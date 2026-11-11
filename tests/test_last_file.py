"""Startup restores the last file unless a file was explicitly requested."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from main import MainWindow


class LastFileTests(unittest.TestCase):
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
        self.windows = []

    def tearDown(self):
        for window in self.windows:
            window.editor.document().setModified(False)
            window.close()
            window.deleteLater()
        self.app.processEvents()

    def window(self, initial_file=None):
        window = MainWindow(initial_file)
        self.windows.append(window)
        return window

    def test_reopens_last_opened_file(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / 'first.md'
            second = Path(directory) / 'second.md'
            first.write_text('First')
            second.write_text('Second')
            window = self.window()
            self.assertIsNone(window.current_file)
            self.assertTrue(window.open_file(first))
            self.assertTrue(window.open_file(second))
            restored = self.window()
            self.assertEqual(restored.current_file, second)
            self.assertEqual(restored.editor.toPlainText(), 'Second')

    def test_explicit_file_takes_priority_and_becomes_last_file(self):
        with tempfile.TemporaryDirectory() as directory:
            previous = Path(directory) / 'previous.md'
            requested = Path(directory) / 'requested.md'
            previous.write_text('Previous')
            requested.write_text('Requested')
            self.window().open_file(previous)
            explicit = self.window(requested)
            self.assertEqual(explicit.current_file, requested)
            self.assertEqual(explicit.editor.toPlainText(), 'Requested')
            self.assertEqual(self.window().current_file, requested)

    def test_saved_untitled_file_restores_and_missing_file_is_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            saved = Path(directory) / 'saved.md'
            window = self.window()
            window.editor.setPlainText('Saved text')
            with patch('main.QFileDialog.getSaveFileName', return_value=(str(saved), 'Markdown (*.md *.markdown)')):
                self.assertTrue(window.save_as())
            self.assertEqual(self.window().current_file, saved)
            saved.unlink()
            self.assertIsNone(self.window().current_file)
