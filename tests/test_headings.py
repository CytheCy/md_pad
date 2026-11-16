"""Heading visibility must affect rendering only, never the source text."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCharFormat, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from main import MarkdownHighlighter, NoteEditor
from themes import THEMES


class HeadingTests(unittest.TestCase):
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

    def marker(self, line):
        block = self.editor.document().findBlockByNumber(line)
        ranges = block.layout().formats()
        return QTextCharFormat(ranges[0].format)

    def test_click_reveals_heading_and_leaving_collapses_it(self):
        source = '# First\n## Second\nBody'
        self.editor.setPlainText(source)
        self.app.processEvents()
        document = self.editor.document()
        before = (document.isModified(), document.availableUndoSteps())
        self.assertEqual(self.marker(0).foreground().color().alpha(), 255)
        self.assertEqual(self.marker(1).foreground().color().alpha(), 0)
        block = document.findBlockByNumber(1)
        layout = block.layout().lineAt(0)
        self.assertLess(layout.cursorToX(3)[0] - layout.cursorToX(0)[0], 1)

        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        QTest.mouseClick(self.editor.viewport(), Qt.MouseButton.LeftButton,
                         pos=self.editor.cursorRect(cursor).center())
        self.app.processEvents()
        self.assertEqual(self.editor.textCursor().blockNumber(), 1)
        self.assertEqual(self.marker(0).foreground().color().alpha(), 0)
        self.assertEqual(self.marker(1).foreground().color().alpha(), 255)
        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        self.assertEqual(self.marker(1).foreground().color().alpha(), 0)
        self.assertEqual(self.editor.toPlainText(), source)
        self.assertEqual((document.isModified(), document.availableUndoSteps()), before)

    def test_code_and_plain_text_keep_markers_visible(self):
        self.editor.setPlainText('```\n# Code\n```\n# Heading\nBody')
        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        self.highlighter.rehighlight()
        self.assertEqual(self.marker(1).foreground().color().alpha(), 255)
        self.assertEqual(self.marker(3).foreground().color().alpha(), 0)
        self.highlighter.enabled = False
        self.highlighter.rehighlight()
        for line in range(5):
            self.assertEqual(self.editor.document().findBlockByNumber(line).layout().formats(), [])

    def test_empty_heading_keeps_hash_visible_when_cursor_leaves(self):
        source = '# \nBody\n## Named'
        self.editor.setPlainText(source)
        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        self.app.processEvents()

        empty = self.editor.document().firstBlock()
        self.assertEqual(self.marker(0).foreground().color().alpha(), 255)
        self.assertGreater(empty.layout().lineAt(0).cursorToX(1)[0]
                           - empty.layout().lineAt(0).cursorToX(0)[0], 1)
        self.assertEqual(self.editor.toPlainText(), source)

        cursor = QTextCursor(empty)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        self.editor.setTextCursor(cursor)
        self.editor.insertPlainText('Title')
        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        self.assertEqual(self.marker(0).foreground().color().alpha(), 0)

        self.editor.undo()
        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        self.assertEqual(self.marker(0).foreground().color().alpha(), 255)
        self.assertEqual(self.editor.toPlainText(), source)

    def test_editing_and_undo_preserve_heading_source(self):
        self.editor.setPlainText('# Heading\nBody')
        self.editor.moveCursor(QTextCursor.MoveOperation.EndOfBlock)
        self.editor.insertPlainText(' changed')
        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        self.editor.undo()
        self.assertEqual(self.editor.toPlainText(), '# Heading\nBody')
        self.editor.redo()
        self.assertEqual(self.editor.toPlainText(), '# Heading changed\nBody')

    def test_paragraph_spacing_survives_document_replacement_at_every_heading_level(self):
        source = '# One\nFirst\nSecond\n## Two\nThird\nFourth\n### Three\nFifth\nSixth'
        self.editor.set_paragraph_spacing(17)
        self.editor.setPlainText(source)
        self.app.processEvents()

        def gaps():
            blocks = [self.editor.document().findBlockByNumber(i) for i in range(9)]
            self.assertTrue(all(block.blockFormat().bottomMargin() == 17 for block in blocks))
            result = []
            for block, next_block in zip(blocks, blocks[1:]):
                end = QTextCursor(block)
                end.movePosition(QTextCursor.MoveOperation.EndOfBlock)
                result.append(self.editor.cursorRect(QTextCursor(next_block)).top()
                              - self.editor.cursorRect(end).bottom() - 1)
            return result

        self.assertEqual(gaps(), [17] * 8)
        self.assertEqual(self.editor.toPlainText(), source)

        self.editor.set_paragraph_spacing(6)
        self.app.processEvents()
        self.assertEqual([self.editor.document().findBlockByNumber(i)
                          .blockFormat().bottomMargin() for i in range(9)], [6] * 9)

        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        QTest.keyClick(self.editor, Qt.Key.Key_Return)
        QTest.keyClicks(self.editor, 'New paragraph')
        self.assertEqual(self.editor.document().lastBlock().blockFormat().bottomMargin(), 6)
