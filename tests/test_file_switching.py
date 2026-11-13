"""Switching notes saves or discards the current note before replacing it."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from main import MainWindow


class FileSwitchingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.first = root / 'first.md'
        self.second = root / 'second.txt'
        self.first.write_text('# First\n' + 'Paragraph\n' * 30 +
                              '```python\nx = 1\n```\n\n'
                              '| Name | Price |\n| --- | --- |\n| One | $1 |\nEnd')
        self.second.write_text('Second')
        self.settings = QSettings(str(root / 'settings.ini'), QSettings.Format.IniFormat)
        with patch('main.QSettings', return_value=self.settings):
            self.window = MainWindow(self.first)
        self.window.show()
        self.app.processEvents()
        self.original = self.first.read_text()

    def tearDown(self):
        self.window._saved_text = self.window.editor.toPlainText()
        self.window.editor.document().setModified(False)
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def edit_first(self):
        self.window.editor.moveCursor(QTextCursor.MoveOperation.End)
        self.window.editor.insertPlainText(' changed')
        return self.window.editor.toPlainText()

    def assert_second_open(self):
        self.assertEqual(self.window.current_file, self.second)
        self.assertEqual(self.window.editor.toPlainText(), 'Second')
        self.assertFalse(self.window.has_unsaved_changes())
        self.assertFalse(self.window.editor.document().isUndoAvailable())
        self.assertEqual(self.settings.value('last_open_file'), str(self.second))

    def test_save_writes_first_before_opening_second(self):
        changed = self.edit_first()
        # Source comparison still catches changes if Qt clears its dirty flag.
        self.window.editor.document().setModified(False)
        with patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.Save) as prompt:
            self.assertTrue(self.window.open_file(self.second))
        prompt.assert_called_once()
        self.assertEqual(self.first.read_text(), changed)
        self.assert_second_open()

    def test_discard_keeps_first_on_disk_and_opens_second(self):
        self.edit_first()
        with patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.Discard):
            self.assertTrue(self.window.open_file(self.second))
        self.assertEqual(self.first.read_text(), self.original)
        self.assert_second_open()

    def test_cancel_or_dismiss_preserves_current_note(self):
        changed = self.edit_first()
        for choice in (QMessageBox.StandardButton.Cancel, 0):
            with self.subTest(choice=choice), patch.object(QMessageBox, 'exec', return_value=choice):
                self.assertFalse(self.window.open_file(self.second))
            self.assertEqual(self.window.current_file, self.first)
            self.assertEqual(self.window.editor.toPlainText(), changed)
            self.assertEqual(self.first.read_text(), self.original)

    def test_save_failure_aborts_switch(self):
        changed = self.edit_first()
        with (patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.Save),
              patch.object(self.window, 'save_file', return_value=False)):
            self.assertFalse(self.window.open_file(self.second))
        self.assertEqual(self.window.current_file, self.first)
        self.assertEqual(self.window.editor.toPlainText(), changed)

    def test_cancel_save_as_preserves_untitled_note(self):
        self.window.new_file()
        self.window.editor.insertPlainText('Untitled changes')
        with (patch.object(QMessageBox, 'exec', return_value=QMessageBox.StandardButton.Save),
              patch('main.QFileDialog.getSaveFileName', return_value=('', ''))):
            self.assertFalse(self.window.open_file(self.second))
        self.assertIsNone(self.window.current_file)
        self.assertEqual(self.window.editor.toPlainText(), 'Untitled changes')

    def test_unreadable_next_file_preserves_current_note(self):
        with patch.object(QMessageBox, 'critical'):
            self.assertFalse(self.window.open_file(self.second.with_name('missing.md')))
        self.assertEqual(self.window.current_file, self.first)
        self.assertEqual(self.window.editor.toPlainText(), self.original)

    def test_switch_releases_active_markdown_and_pending_work(self):
        editor = self.window.editor
        for _ in range(3):
            for text in ('x = 1', '| One | $1 |'):
                editor.setTextCursor(editor.document().find(text))
                editor.update_code_panels()
                editor.spelling.refresh()
                editor.schedule_code_panel_update()
                with patch.object(QMessageBox, 'exec') as prompt:
                    self.assertTrue(self.window.open_file(self.second))
                prompt.assert_not_called()
                QTest.qWait(300)
                self.assert_second_open()
                self.assertEqual(editor.code_panels, [])
                self.assertEqual(editor.table_regions, [])
                self.assertEqual(editor._panel_blocks, {})
                self.assertEqual(editor._code_selections, [])
                self.assertEqual(editor._table_selections, [])
                self.assertEqual(self.first.read_text(), self.original)
                self.assertTrue(self.window.open_file(self.first))
                self.app.processEvents()
                self.assertTrue(editor.code_panels)
                self.assertTrue(editor.table_regions)
