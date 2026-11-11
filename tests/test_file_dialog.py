"""File opening uses KDE's chooser when the desktop provides it."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

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

    def test_kde_dialog_opens_selected_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'chosen.md'
            path.write_text('Chosen')
            with (patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'KDE'}),
                  patch('main.shutil.which', return_value='/usr/bin/kdialog'),
                  patch('main.subprocess.run', return_value=subprocess.CompletedProcess([], 0, str(path) + '\n')) as run,
                  patch('main.QFileDialog.getOpenFileName') as qt_dialog):
                self.window.choose_file()
            self.assertEqual(self.window.current_file, path)
            self.assertEqual(self.window.editor.toPlainText(), 'Chosen')
            self.assertIn('--getopenfilename', run.call_args.args[0])
            qt_dialog.assert_not_called()

    def test_kde_dialog_cancel_does_not_open_qt_dialog(self):
        with (patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'KDE'}),
              patch('main.shutil.which', return_value='/usr/bin/kdialog'),
              patch('main.subprocess.run', return_value=subprocess.CompletedProcess([], 1, '')),
              patch('main.QFileDialog.getOpenFileName') as qt_dialog):
            self.window.choose_file()
        self.assertIsNone(self.window.current_file)
        qt_dialog.assert_not_called()

    def test_qt_dialog_remains_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'chosen.md'
            path.write_text('Chosen')
            with (patch.dict(os.environ, {'XDG_CURRENT_DESKTOP': 'KDE'}),
                  patch('main.shutil.which', return_value=None),
                  patch('main.QFileDialog.getOpenFileName', return_value=(str(path), '')) as qt_dialog):
                self.window.choose_file()
            self.assertEqual(self.window.current_file, path)
            qt_dialog.assert_called_once()
