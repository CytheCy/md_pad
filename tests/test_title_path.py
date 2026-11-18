"""The title hover card follows the current file and keeps its actions usable."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QEvent, QPoint, QSettings, Qt, QUrl
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication

from main import MainWindow


class TitlePathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'a file #1.md'
        self.path.write_text('Hello')
        settings = QSettings(str(Path(self.temp.name) / 'settings.ini'), QSettings.Format.IniFormat)
        with patch('main.QSettings', return_value=settings):
            self.window = MainWindow(self.path)
        self.window.show()
        self.window.activateWindow()
        self.app.processEvents()
        self.popup = self.window.document_path_popup

    def tearDown(self):
        self.window._saved_text = self.window.editor.toPlainText()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def test_hover_and_actions_preserve_editor_focus(self):
        self.assertTrue(QTest.qWaitForWindowActive(self.window))
        self.window.editor.setFocus()
        hover_timeout = QSignalSpy(self.popup.show_timer.timeout)
        self.app.sendEvent(self.window.title_label, QEvent(QEvent.Type.Enter))
        self.assertTrue(hover_timeout.wait(2000), 'Document path hover timer did not fire')
        self.assertTrue(self.popup.isVisible())
        self.assertEqual(self.popup.path_label.text(), str(self.path))
        self.assertIs(self.app.focusWidget(), self.window.editor)
        # Leaving the title gives time to move onto the card and its buttons.
        self.app.sendEvent(self.window.title_label, QEvent(QEvent.Type.Leave))
        self.assertTrue(self.popup.isVisible())
        self.app.sendEvent(self.popup, QEvent(QEvent.Type.Enter))
        self.assertFalse(self.popup.hide_timer.isActive())
        QTest.mouseClick(self.popup.copy_button, Qt.MouseButton.LeftButton)
        self.assertEqual(self.app.clipboard().text(), str(self.path))
        with patch('main.QDesktopServices.openUrl', return_value=True) as open_url:
            QTest.mouseClick(self.popup.folder_button, Qt.MouseButton.LeftButton)
        open_url.assert_called_once_with(QUrl.fromLocalFile(str(self.path.parent)))
        self.assertFalse(self.popup.isVisible())

    def test_switch_new_and_save_as_refresh_path(self):
        other = self.path.with_name('other.txt')
        other.write_text('Other')
        self.window.open_file(other)
        self.assertEqual(self.popup.path_label.text(), str(other))
        self.window.new_file()
        self.assertEqual(self.popup.path_label.text(), 'Not saved yet')
        self.assertFalse(self.popup.copy_button.isEnabled())
        self.assertFalse(self.popup.folder_button.isEnabled())
        saved = self.path.with_name('saved.md')
        with patch('main.QFileDialog.getSaveFileName', return_value=(str(saved), 'All files (*)')):
            self.assertTrue(self.window.save_as())
        self.assertEqual(self.popup.path_label.text(), str(saved))
        self.assertTrue(self.popup.copy_button.isEnabled())
        self.assertTrue(self.popup.folder_button.isEnabled())

    def test_escape_move_and_close_dismiss_card(self):
        self.popup.show_for_title()
        QTest.keyClick(self.window.editor, Qt.Key.Key_Escape)
        self.assertFalse(self.popup.isVisible())
        self.popup.show_for_title()
        self.window.move(self.window.x() + 10, self.window.y() + 10)
        self.app.processEvents()
        self.assertFalse(self.popup.isVisible())
        self.popup.show_for_title()
        self.window.close()
        self.assertFalse(self.popup.isVisible())

    def test_leaving_card_dismisses_after_grace_period(self):
        self.popup.show_for_title()
        outside = self.window.editor.mapToGlobal(QPoint(50, 200))
        hide_timeout = QSignalSpy(self.popup.hide_timer.timeout)
        with patch('main.QCursor.pos', return_value=outside):
            self.app.sendEvent(self.popup, QEvent(QEvent.Type.Leave))
            self.assertTrue(self.popup.isVisible())
            self.assertTrue(hide_timeout.wait(2000), 'Document path hide timer did not fire')
        self.assertFalse(self.popup.isVisible())


if __name__ == '__main__':
    unittest.main()
