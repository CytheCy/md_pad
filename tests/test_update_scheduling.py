"""Source edits schedule work; display formatting and idle time do not."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication

from main import MainWindow


class UpdateSchedulingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        settings = QSettings(str(Path(self.temp.name) / 'settings.ini'),
                             QSettings.Format.IniFormat)
        with patch('main.QSettings', return_value=settings):
            self.window = MainWindow()
        self.editor = self.window.editor
        self.window.show()
        self.settle()

    def tearDown(self):
        self.editor.document().setModified(False)
        self.window._saved_text = self.editor.toPlainText()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def settle(self):
        for _ in range(6):
            self.app.processEvents()

    def test_large_note_stops_highlighting_when_idle(self):
        source = '\n'.join(f'# Heading {i}\nSome ordinary paragraph words.'
                           for i in range(1000))
        self.editor.setPlainText(source)
        self.settle()
        self.editor.spelling.refresh()
        document = self.editor.document()
        document.setModified(False)
        before = (self.editor.toPlainText(), document.availableUndoSteps())
        with patch.object(self.window.highlighter, 'rehighlight',
                          wraps=self.window.highlighter.rehighlight) as highlight:
            self.settle()
            self.editor.moveCursor(QTextCursor.MoveOperation.NextBlock)
            self.settle()
            self.editor.moveCursor(QTextCursor.MoveOperation.End)
            self.settle()
            highlight.assert_not_called()
        self.assertFalse(self.editor._code_update_timer.isActive())
        self.assertFalse(self.editor.spelling.timer.isActive())
        self.assertEqual((self.editor.toPlainText(), document.availableUndoSteps()), before)
        self.assertFalse(document.isModified())

    def test_display_changes_do_not_notify_source_consumers(self):
        self.editor.setPlainText('# First\nBody\n## Second\n```\ncode\n```')
        self.settle()
        self.editor.spelling.refresh()
        changes = []
        self.editor.sourceChanged.connect(lambda: changes.append(True))
        with patch.object(self.window, 'update_status') as status:
            self.window.highlighter.rehighlight()
            self.editor.moveCursor(QTextCursor.MoveOperation.End)
            self.settle()
            self.assertFalse(self.editor._code_update_timer.isActive())
            self.editor.set_paragraph_spacing(12)
            self.window.set_font_size(16)
            self.window.set_theme('tokyo-night')
            self.settle()
            status.assert_not_called()
        self.assertEqual(changes, [])
        self.assertFalse(self.editor.spelling.timer.isActive())
        self.assertFalse(self.editor._code_update_timer.isActive())
        self.assertEqual(len(self.editor.code_panels), 1)

    def test_character_edits_only_highlight_local_blocks(self):
        self.editor.setPlainText('\n'.join(
            f'# Heading {i}\nSome ordinary paragraph words.' for i in range(1000)))
        self.settle()
        self.editor.moveCursor(QTextCursor.MoveOperation.NextBlock)
        self.settle()
        highlighter = self.window.highlighter
        with patch.object(highlighter, 'rehighlight', wraps=highlighter.rehighlight) as full:
            with patch.object(highlighter, 'highlightBlock',
                              wraps=highlighter.highlightBlock) as blocks:
                self.editor.insertPlainText('x')
                self.settle()
                self.editor.textCursor().deletePreviousChar()
                self.settle()
                full.assert_not_called()
                self.assertGreater(blocks.call_count, 0)
                self.assertLess(blocks.call_count, 20)
        self.assertFalse(self.editor._code_update_timer.isActive())

    def test_same_length_edits_undo_redo_and_clear_still_update(self):
        self.editor.setPlainText('# First\n## Second')
        self.settle()
        cursor = self.editor.textCursor()
        cursor.setPosition(2)
        cursor.setPosition(7, QTextCursor.MoveMode.KeepAnchor)
        self.editor.setTextCursor(cursor)
        self.editor.insertPlainText('Other')
        self.assertEqual(self.window.headings[0][2], 'Other')
        self.assertTrue(self.editor.spelling.timer.isActive())
        self.settle()
        self.assertFalse(self.editor._code_update_timer.isActive())
        self.editor.undo()
        self.assertEqual(self.window.headings[0][2], 'First')
        self.editor.redo()
        self.assertEqual(self.window.headings[0][2], 'Other')
        self.editor.clear()
        self.assertEqual(self.window.headings, [])
        self.assertEqual(self.window.count_label.text(), '0 words')
        self.settle()
        self.assertFalse(self.editor._code_update_timer.isActive())

    def test_typing_only_rechecks_edited_paragraph_for_headings(self):
        self.editor.setPlainText('\n'.join(
            f'# Heading {i}\nSome ordinary paragraph words.' for i in range(1000)))
        self.settle()
        self.editor.moveCursor(QTextCursor.MoveOperation.NextBlock)
        w = self.window
        with patch.object(w, 'parse_heading_block', wraps=w.parse_heading_block) as parse:
            with patch.object(w, 'discover_headings', wraps=w.discover_headings) as discover:
                for character in 'typing words':
                    self.editor.insertPlainText(character)
                    self.app.processEvents()
                self.assertEqual(parse.call_count, 12)
                self.assertTrue(all(call.kwargs['full'] is False for call in discover.call_args_list))
                self.editor.textCursor().deletePreviousChar()
                self.assertEqual(parse.call_count, 13)


if __name__ == '__main__':
    unittest.main()
