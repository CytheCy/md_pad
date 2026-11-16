"""Window placement and maximization survive closing and reopening."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QRect, QSettings, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from main import MainWindow, configure_window_platform


class WindowPlatformTests(unittest.TestCase):
    def test_platform_selection_preserves_explicit_choices_and_wayland_only_sessions(self):
        cases = [
            ({'WAYLAND_DISPLAY': 'wayland-0', 'DISPLAY': ':0'}, 'xcb;wayland'),
            ({'WAYLAND_DISPLAY': 'wayland-0'}, None),
            ({'WAYLAND_DISPLAY': 'wayland-0', 'DISPLAY': ':0',
              'QT_QPA_PLATFORM': 'offscreen'}, 'offscreen'),
        ]
        for environment, expected in cases:
            with self.subTest(environment=environment):
                with patch.dict(os.environ, environment, clear=True), patch('main.sys.platform', 'linux'):
                    configure_window_platform()
                    self.assertEqual(os.environ.get('QT_QPA_PLATFORM'), expected)


class WindowGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings_path = str(Path(self.temp.name) / 'settings.ini')
        self.windows = []

    def tearDown(self):
        for window in self.windows:
            window.close()
            window.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def open_window(self):
        settings = QSettings(self.settings_path, QSettings.Format.IniFormat)
        with patch('main.QSettings', return_value=settings):
            window = MainWindow()
        self.windows.append(window)
        window.show()
        self.app.processEvents()
        return window

    def place_window(self, window):
        window.resize(700, 500)
        window.move(40, 60)
        self.app.processEvents()
        return window.geometry()

    def test_restores_normal_size_and_position(self):
        window = self.open_window()
        geometry = self.place_window(window)
        self.assertTrue(window.close())

        restored = self.open_window()
        self.assertFalse(restored.isMaximized())
        self.assertEqual(restored.geometry(), geometry)

    def test_restores_window_aligned_to_right_screen_edge(self):
        window = self.open_window()
        area = window.screen().availableGeometry()
        width = max(window.minimumWidth(), area.width() // 2)
        geometry = QRect(area.right() - width + 1, area.top(), width, area.height())
        window.setGeometry(geometry)
        self.app.processEvents()
        self.assertEqual(window.geometry(), geometry)
        self.assertTrue(window.close())

        restored = self.open_window()
        self.assertEqual(restored.geometry(), geometry)
        restored.showMaximized()
        self.app.processEvents()
        self.assertTrue(restored.close())

        maximized = self.open_window()
        self.assertTrue(maximized.isMaximized())
        maximized.showNormal()
        self.app.processEvents()
        self.assertEqual(maximized.geometry(), geometry)

    def test_restores_maximized_state_and_previous_normal_geometry(self):
        window = self.open_window()
        geometry = self.place_window(window)
        window.showMaximized()
        self.app.processEvents()
        self.assertTrue(window.close())

        restored = self.open_window()
        self.assertTrue(restored.isMaximized())
        self.assertEqual(restored.maximize_button.icon_name, 'windows')
        restored.showNormal()
        self.app.processEvents()
        self.assertEqual(restored.geometry(), geometry)
        self.assertTrue(restored.close())

        normal = self.open_window()
        self.assertFalse(normal.isMaximized())
        self.assertEqual(normal.geometry(), geometry)

    def test_cancelled_close_does_not_replace_saved_geometry(self):
        window = self.open_window()
        self.place_window(window)
        self.assertTrue(window.close())
        saved = window.settings.value('window_geometry')
        saved_normal = window.settings.value('window_normal_geometry')
        window = self.open_window()
        window.move(10, 20)
        with patch.object(window, 'confirm_discard', return_value=False):
            self.assertFalse(window.close())
        self.assertEqual(window.settings.value('window_geometry'), saved)
        self.assertEqual(window.settings.value('window_normal_geometry'), saved_normal)

    def click_close_through_menu(self, window, menu):
        self.assertIs(self.app.activePopupWidget(), menu)
        # Popup menus receive even clicks outside their own rectangle.
        position = menu.mapFromGlobal(window.close_button.mapToGlobal(
            window.close_button.rect().center()))
        QTest.mouseClick(menu, Qt.MouseButton.LeftButton, pos=position)
        self.app.processEvents()

    def test_close_button_works_with_each_menu_open(self):
        for name in ('file_menu', 'settings_menu', 'recent_menu', 'heading_panel_menu'):
            with self.subTest(menu=name):
                window = self.open_window()
                menu = getattr(window, name)
                parent_menu = (window.file_menu if name == 'recent_menu' else
                               window.settings_menu if name == 'heading_panel_menu' else None)
                if parent_menu:
                    parent_menu.popup(window.menuBar().mapToGlobal(
                        window.menuBar().actionGeometry(parent_menu.menuAction()).bottomLeft()))
                menu.popup(window.menuBar().mapToGlobal(
                    window.menuBar().actionGeometry(window.file_menu.menuAction()).bottomLeft()))
                self.app.processEvents()
                with patch.object(window, 'confirm_discard', return_value=True) as confirm:
                    self.click_close_through_menu(window, menu)
                confirm.assert_called_once()
                self.assertFalse(window.isVisible())
                self.assertFalse(menu.isVisible())
                if parent_menu:
                    self.assertFalse(parent_menu.isVisible())

    def test_close_from_menu_can_be_cancelled_for_unsaved_changes(self):
        window = self.open_window()
        window.editor.setPlainText('Unsaved note')
        window.file_menu.popup(window.menuBar().mapToGlobal(
            window.menuBar().actionGeometry(window.file_menu.menuAction()).bottomLeft()))
        self.app.processEvents()
        with patch.object(window, 'confirm_discard', return_value=False) as confirm:
            self.click_close_through_menu(window, window.file_menu)
        confirm.assert_called_once()
        self.assertTrue(window.isVisible())
        self.assertFalse(window.file_menu.isVisible())
        self.assertEqual(window.editor.toPlainText(), 'Unsaved note')
        window.editor.setPlainText('')

    def test_close_hover_matches_normal_appearance_with_menus_open(self):
        window = self.open_window()
        button = window.close_button
        QTest.mouseMove(window.editor, window.editor.rect().center())
        self.app.processEvents()
        normal = button.grab().toImage()
        QTest.mouseMove(button, button.rect().center())
        self.app.processEvents()
        hovered = button.grab().toImage()
        self.assertNotEqual(normal, hovered)
        self.assertEqual(hovered.pixelColor(4, 4), QColor(window.theme['error']))

        for name in ('file_menu', 'settings_menu', 'recent_menu', 'heading_panel_menu'):
            with self.subTest(menu=name):
                menu = getattr(window, name)
                menu.popup(window.menuBar().mapToGlobal(
                    window.menuBar().actionGeometry(window.file_menu.menuAction()).bottomLeft()))
                self.app.processEvents()
                QTest.mouseMove(menu, menu.rect().center())
                self.app.processEvents()
                self.assertFalse(button.underMouse())
                self.assertEqual(button.grab().toImage(), normal)

                position = menu.mapFromGlobal(button.mapToGlobal(button.rect().center()))
                QTest.mouseMove(menu, position)
                self.app.processEvents()
                self.assertTrue(menu.isVisible())
                self.assertTrue(button.underMouse())
                self.assertEqual(button.grab().toImage(), hovered)

                QTest.mouseMove(menu, menu.rect().center())
                self.app.processEvents()
                self.assertEqual(button.grab().toImage(), normal)
                menu.close()
                self.app.processEvents()
                self.assertFalse(button.underMouse())

        # Dismissing a menu over the close control must leave normal hover
        # behavior working when the pointer subsequently leaves the button.
        window.file_menu.popup(window.menuBar().mapToGlobal(
            window.menuBar().actionGeometry(window.file_menu.menuAction()).bottomLeft()))
        self.app.processEvents()
        QTest.mouseMove(window.file_menu, window.file_menu.mapFromGlobal(
            button.mapToGlobal(button.rect().center())))
        window.file_menu.close()
        self.app.processEvents()
        self.assertEqual(button.grab().toImage(), hovered)
        QTest.mouseMove(window.editor, window.editor.rect().center())
        self.app.processEvents()
        self.assertEqual(button.grab().toImage(), normal)

    def test_minimized_window_reopens_visible(self):
        window = self.open_window()
        geometry = self.place_window(window)
        window.showMinimized()
        self.app.processEvents()
        self.assertTrue(window.close())

        restored = self.open_window()
        self.assertFalse(restored.isMinimized())
        self.assertEqual(restored.geometry(), geometry)


if __name__ == '__main__':
    unittest.main()
