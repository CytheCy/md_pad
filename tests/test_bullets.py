"""Enter continues Markdown bullets and exits without a blank source line."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCharFormat, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from main import MarkdownHighlighter, NoteEditor
from themes import THEMES


class BulletTests(unittest.TestCase):
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

    def enter(self):
        QTest.keyClick(self.editor, Qt.Key.Key_Return)

    def test_bullet_markers_continue_then_exit_with_one_newline(self):
        for marker in '-*+':
            with self.subTest(marker=marker):
                self.editor.setPlainText(f'{marker} first')
                self.editor.moveCursor(QTextCursor.MoveOperation.End)
                self.enter()
                self.assertEqual(self.editor.toPlainText(), f'{marker} first\n{marker} ')
                QTest.keyClicks(self.editor, 'second')
                self.enter()
                self.assertEqual(self.editor.toPlainText(),
                                 f'{marker} first\n{marker} second\n{marker} ')
                self.enter()
                self.assertEqual(self.editor.toPlainText(),
                                 f'{marker} first\n{marker} second\n')
                QTest.keyClicks(self.editor, 'body')
                self.assertEqual(self.editor.toPlainText(),
                                 f'{marker} first\n{marker} second\nbody')

    def test_empty_bullet_exits_without_inserting_newline(self):
        self.editor.setPlainText('- ')
        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        self.enter()
        self.assertEqual(self.editor.toPlainText(), '')

    def test_other_lines_keep_normal_enter_behavior(self):
        self.editor.setPlainText('-without space')
        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        self.enter()
        self.assertEqual(self.editor.toPlainText(), '-without space\n')

    def test_inactive_bullet_hides_source_marker_and_active_bullet_shows_it(self):
        highlighter = MarkdownHighlighter(
            self.editor.document(), THEMES['catppuccin-mocha'], self.editor)
        source = '- See\n* Another\n```\n+ code\n```'
        self.editor.setPlainText(source)
        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        self.app.processEvents()
        document = self.editor.document()
        document.setModified(False)
        before = document.availableUndoSteps()

        def marker_alpha(line):
            block = document.findBlockByNumber(line)
            ranges = block.layout().formats()
            return QTextCharFormat(ranges[0].format).foreground().color().alpha()

        self.assertEqual(marker_alpha(0), 0)
        self.assertEqual(marker_alpha(1), 0)
        self.assertEqual(marker_alpha(3), 255)
        cursor = QTextCursor(document.findBlockByNumber(0))
        self.editor.setTextCursor(cursor)
        self.app.processEvents()
        self.assertEqual(marker_alpha(0), 255)
        self.assertEqual(marker_alpha(1), 0)
        self.assertEqual(self.editor.toPlainText(), source)
        self.assertFalse(document.isModified())
        self.assertEqual(document.availableUndoSteps(), before)


if __name__ == '__main__':
    unittest.main()
