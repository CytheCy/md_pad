"""Window placement and maximization survive closing and reopening."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QRect, QSettings
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
