"""Code delimiters hide visually while their Markdown source stays editable."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest

from PySide6.QtGui import QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QApplication

from main import MarkdownHighlighter, NoteEditor
from themes import THEMES


class CodeMarkerTests(unittest.TestCase):
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

    def test_inline_backticks_collapse_and_reappear_on_active_line(self):
        source = 'Before `code` and ``long``\nAfter'
        self.editor.setPlainText(source)
        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        self.app.processEvents()
        document = self.editor.document()
        document.setModified(False)
        before = document.availableUndoSteps()

        for offset in (7, 12, 18, 19, 24, 25):
            self.assertEqual(self.format_at(0, offset).foreground().color().alpha(), 0)
        self.assertEqual(self.format_at(0, 8).fontFamilies(), ['monospace'])
        line = document.firstBlock().layout().lineAt(0)
        self.assertLess(line.cursorToX(8)[0] - line.cursorToX(7)[0], 1)

        self.editor.setTextCursor(QTextCursor(document.firstBlock()))
        self.app.processEvents()
        self.assertEqual(self.format_at(0, 7).foreground().color().alpha(), 255)
        self.assertEqual(self.format_at(0, 18).foreground().color().alpha(), 255)
        self.assertEqual(self.editor.toPlainText(), source)
        self.assertFalse(document.isModified())
        self.assertEqual(document.availableUndoSteps(), before)

    def test_fenced_lines_hide_and_reappear_while_code_remains_styled(self):
        source = 'Before\n```python\nx = *literal*\n```\nAfter'
        self.editor.setPlainText(source)
        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        self.app.processEvents()
        document = self.editor.document()
        document.setModified(False)
        before = document.availableUndoSteps()

        self.assertEqual(self.format_at(1, 0).foreground().color().alpha(), 0)
        self.assertEqual(self.format_at(3, 0).foreground().color().alpha(), 0)
        self.assertEqual(self.format_at(2, 4).foreground().color().alpha(), 255)
        self.assertFalse(self.format_at(2, 4).fontItalic())
        self.editor.setTextCursor(QTextCursor(document.findBlockByNumber(1)))
        self.app.processEvents()
        self.assertEqual(self.format_at(1, 0).foreground().color().alpha(), 255)
        self.assertEqual(self.format_at(3, 0).foreground().color().alpha(), 255)
        self.editor.setTextCursor(QTextCursor(document.findBlockByNumber(2)))
        self.app.processEvents()
        self.assertEqual(self.format_at(1, 0).foreground().color().alpha(), 255)
        self.assertEqual(self.format_at(3, 0).foreground().color().alpha(), 255)
        self.editor.setTextCursor(QTextCursor(document.firstBlock()))
        self.app.processEvents()
        self.assertEqual(self.format_at(1, 0).foreground().color().alpha(), 0)
        self.assertEqual(self.format_at(3, 0).foreground().color().alpha(), 0)
        self.assertEqual(self.editor.toPlainText(), source)
        self.assertFalse(document.isModified())
        self.assertEqual(document.availableUndoSteps(), before)

    def test_editing_a_fence_propagates_code_style_and_undo_restores_it(self):
        self.editor.setPlainText('Before\n``\n# Heading\n```\nAfter')
        self.app.processEvents()
        document = self.editor.document()
        cursor = QTextCursor(document.findBlockByNumber(1))
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        self.editor.setTextCursor(cursor)
        self.editor.insertPlainText('`')
        self.app.processEvents()
        self.assertEqual([document.findBlockByNumber(i).userState() for i in range(5)],
                         [0, 1, 1, 0, 0])
        self.assertEqual(self.format_at(2, 2).fontFamilies(), ['monospace'])
        self.assertEqual(len(self.editor.code_panels), 1)
        self.editor.undo()
        self.app.processEvents()
        self.assertEqual([document.findBlockByNumber(i).userState() for i in range(5)],
                         [0, 0, 0, 1, 1])
        self.assertTrue(self.format_at(2, 2).font().bold())
        self.assertEqual(self.editor.toPlainText(), 'Before\n``\n# Heading\n```\nAfter')


if __name__ == '__main__':
    unittest.main()
