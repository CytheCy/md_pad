"""File opening uses the KDE portal picker when available."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox

from main import MainWindow


class FileDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, cls.temp.name)
        cls.app = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        QSettings('Pad', 'Pad').clear()
        self.window = MainWindow()

    def tearDown(self):
        self.window.editor.document().setModified(False)
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_kde_portal_opens_selected_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'chosen.md'
            path.write_text('Chosen')
            with (patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'KDE'}),
                  patch('main.kde_open_file', return_value=(True, str(path))) as portal,
                  patch('main.QFileDialog.getOpenFileName') as qt_dialog):
                self.window.choose_file()
            self.assertEqual(self.window.current_file, path)
            self.assertEqual(self.window.editor.toPlainText(), 'Chosen')
            portal.assert_called_once_with(Path.home())
            qt_dialog.assert_not_called()

    def test_kde_portal_cancel_does_not_open_qt_dialog(self):
        with (patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'KDE'}),
              patch('main.kde_open_file', return_value=(True, '')),
              patch('main.QFileDialog.getOpenFileName') as qt_dialog):
            self.window.choose_file()
        self.assertIsNone(self.window.current_file)
        qt_dialog.assert_not_called()

    def test_qt_dialog_remains_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'chosen.md'
            path.write_text('Chosen')
            with (patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'KDE'}),
                  patch('main.kde_open_file', return_value=(False, '')),
                  patch('main.QFileDialog.getOpenFileName', return_value=(str(path), '')) as qt_dialog):
                self.window.choose_file()
            self.assertEqual(self.window.current_file, path)
            qt_dialog.assert_called_once()

    def test_unsaved_changes_dialog_has_no_question_icon(self):
        self.window.editor.insertPlainText('Unsaved text')

        def cancel(dialog):
            self.assertEqual(dialog.icon(), QMessageBox.Icon.NoIcon)
            self.assertEqual(dialog.windowTitle(), 'Unsaved changes')
            self.assertEqual(dialog.standardButtons(),
                             QMessageBox.StandardButton.Save |
                             QMessageBox.StandardButton.Discard |
                             QMessageBox.StandardButton.Cancel)
            self.assertEqual(dialog.standardButton(dialog.defaultButton()),
                             QMessageBox.StandardButton.Save)
            return QMessageBox.StandardButton.Cancel

        with patch.object(QMessageBox, 'exec', cancel):
            self.assertFalse(self.window.confirm_discard())
        self.assertTrue(self.window.editor.document().isModified())
