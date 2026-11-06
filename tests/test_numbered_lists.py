"""Numbered lists keep editable Markdown source and continue on Enter."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCharFormat, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from main import MarkdownHighlighter, NoteEditor
from themes import THEMES


class NumberedListTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.editor = NoteEditor()
        self.editor.show()
        self.editor.setFocus()

    def tearDown(self):
        self.editor.close()
        self.editor.deleteLater()
        self.app.processEvents()

    def test_enter_increments_and_empty_item_exits_with_one_newline(self):
        for first, second in [('1.', '2.'), ('9)', '10)'), ('01.', '02.')]:
            with self.subTest(first=first):
                self.editor.setPlainText(f'{first} First')
                self.editor.moveCursor(QTextCursor.MoveOperation.End)
                QTest.keyClick(self.editor, Qt.Key.Key_Return)
                self.assertEqual(self.editor.toPlainText(), f'{first} First\n{second} ')
                QTest.keyClick(self.editor, Qt.Key.Key_Return)
                self.assertEqual(self.editor.toPlainText(), f'{first} First\n')
                QTest.keyClicks(self.editor, 'Body')
                self.assertEqual(self.editor.toPlainText(), f'{first} First\nBody')

    def test_inactive_number_hides_source_marker_and_cursor_restores_it(self):
        MarkdownHighlighter(self.editor.document(), THEMES['catppuccin-mocha'], self.editor)
        source = '1. First\n12) Another\n```\n3. code\n```'
        self.editor.setPlainText(source)
        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        self.app.processEvents()
        document = self.editor.document()
        document.setModified(False)
        before = document.availableUndoSteps()

        def marker_alpha(line):
            ranges = document.findBlockByNumber(line).layout().formats()
            return QTextCharFormat(ranges[0].format).foreground().color().alpha()

        self.assertEqual(marker_alpha(0), 0)
        self.assertEqual(marker_alpha(1), 0)
        self.assertEqual(marker_alpha(3), 255)
        self.editor.setTextCursor(QTextCursor(document.findBlockByNumber(1)))
        self.app.processEvents()
        self.assertEqual(marker_alpha(1), 255)
        self.assertEqual(marker_alpha(0), 0)
        self.assertEqual(self.editor.toPlainText(), source)
        self.assertFalse(document.isModified())
        self.assertEqual(document.availableUndoSteps(), before)


if __name__ == '__main__':
    unittest.main()
