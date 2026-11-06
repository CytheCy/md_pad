"""Inline emphasis hides only its source markers away from the cursor."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest

from PySide6.QtGui import QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QApplication

from main import MarkdownHighlighter, NoteEditor
from themes import THEMES


class EmphasisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.editor = NoteEditor()
        self.highlighter = MarkdownHighlighter(
            self.editor.document(), THEMES['catppuccin-mocha'], self.editor)
        self.editor.resize(600, 400)
        self.editor.show()

    def tearDown(self):
        self.editor.close()
        self.editor.deleteLater()
        self.app.processEvents()

    def format_at(self, line, offset):
        block = self.editor.document().findBlockByNumber(line)
        for item in block.layout().formats():
            if item.start <= offset < item.start + item.length:
                return QTextCharFormat(item.format)
        return QTextCharFormat()

    def test_inactive_markers_collapse_and_active_markers_reappear(self):
        source = '😀 *italic* **bold**\n_other_ and __strong__\nBody'
        self.editor.setPlainText(source)
        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        self.app.processEvents()
        document = self.editor.document()
        document.setModified(False)
        before = document.availableUndoSteps()

        for line, offsets in [(0, (3, 10, 12, 13, 18, 19)),
                              (1, (0, 6, 12, 13, 20, 21))]:
            for offset in offsets:
                with self.subTest(line=line, offset=offset):
                    self.assertEqual(self.format_at(line, offset).foreground().color().alpha(), 0)
        self.assertTrue(self.format_at(0, 4).fontItalic())
        self.assertEqual(self.format_at(0, 14).fontWeight(), QFont.Weight.Bold)
        line = document.firstBlock().layout().lineAt(0)
        self.assertLess(line.cursorToX(4)[0] - line.cursorToX(3)[0], 1)
        self.assertLess(line.cursorToX(14)[0] - line.cursorToX(12)[0], 1)

        self.editor.setTextCursor(QTextCursor(document.firstBlock()))
        self.app.processEvents()
        self.assertEqual(self.format_at(0, 3).foreground().color().alpha(), 255)
        self.assertEqual(self.format_at(0, 12).foreground().color().alpha(), 255)
        self.assertEqual(self.format_at(1, 0).foreground().color().alpha(), 0)
        self.assertEqual(self.editor.toPlainText(), source)
        self.assertFalse(document.isModified())
        self.assertEqual(document.availableUndoSteps(), before)

    def test_code_keeps_emphasis_literal_and_plain_text_shows_marks(self):
        source = '`*literal*`\n```\n**code**\n```\n*styled*'
        self.editor.setPlainText(source)
        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        self.app.processEvents()
        self.assertFalse(self.format_at(0, 1).fontItalic())
        self.assertEqual(self.format_at(2, 0).foreground().color().alpha(), 255)
        self.highlighter.enabled = False
        self.highlighter.rehighlight()
        for line in range(5):
            self.assertEqual(self.editor.document().findBlockByNumber(line).layout().formats(), [])


if __name__ == '__main__':
    unittest.main()
