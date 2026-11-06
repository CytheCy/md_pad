"""Clicking web links opens them without changing the note."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from main import MarkdownHighlighter, NoteEditor, web_link_at
from themes import THEMES


class LinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.editor = NoteEditor()
        self.highlighter = MarkdownHighlighter(
            self.editor.document(), THEMES['catppuccin-mocha'], self.editor)
        self.editor.resize(800, 400)
        self.editor.show()

    def tearDown(self):
        self.editor.close()
        self.editor.deleteLater()
        self.app.processEvents()

    def character_point(self, line, offset):
        block = self.editor.document().findBlockByNumber(line)
        start = QTextCursor(block)
        start.setPosition(block.position() + offset)
        end = QTextCursor(block)
        end.setPosition(block.position() + offset + 1)
        left = self.editor.cursorRect(start)
        right = self.editor.cursorRect(end)
        point = left.center()
        point.setX((left.left() + right.left()) // 2)
        return point

    def click_character(self, line, offset):
        QTest.mouseClick(self.editor.viewport(), Qt.MouseButton.LeftButton,
                         pos=self.character_point(line, offset))

    def test_hand_cursor_persists_while_hovering(self):
        self.editor.setPlainText('See [Fedora](https://fedoraproject.org) here')
        self.app.processEvents()
        QTest.mouseMove(self.editor.viewport(), self.character_point(0, 6))
        self.app.processEvents()
        self.assertEqual(QApplication.overrideCursor().shape(),
                         Qt.CursorShape.PointingHandCursor)
        QTest.qWait(100)
        self.assertEqual(QApplication.overrideCursor().shape(),
                         Qt.CursorShape.PointingHandCursor)
        QTest.mouseMove(self.editor.viewport(), self.character_point(0, 1))
        self.app.processEvents()
        self.assertIsNone(QApplication.overrideCursor())

    def test_closing_editor_releases_hover_cursor(self):
        self.editor.setPlainText('https://fedoraproject.org')
        self.app.processEvents()
        QTest.mouseMove(self.editor.viewport(), self.character_point(0, 5))
        self.assertIsNotNone(QApplication.overrideCursor())
        self.editor.close()
        self.app.processEvents()
        self.assertIsNone(QApplication.overrideCursor())

    def test_markdown_and_bare_urls_open_with_desktop_handler(self):
        source = ('See [Fedora](https://fedoraproject.org) and '
                  'https://kde.org/docs.\n`https://example.org`\n'
                  '```\nhttps://example.org\n```')
        self.editor.setPlainText(source)
        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        self.app.processEvents()
        self.editor.document().setModified(False)
        with patch('main.QDesktopServices.openUrl') as open_url:
            self.click_character(0, 6)
            self.click_character(0, source.index('kde.org'))
            self.click_character(1, 5)
            self.click_character(3, 5)
        self.assertEqual([call.args[0].toString() for call in open_url.call_args_list],
                         ['https://fedoraproject.org', 'https://kde.org/docs'])
        self.assertEqual(self.editor.toPlainText(), source)
        self.assertFalse(self.editor.document().isModified())

    def test_url_detection_excludes_code_and_trailing_punctuation(self):
        self.assertIsNone(web_link_at('`https://example.org`', 5))
        self.assertEqual(web_link_at('https://example.org).', 10),
                         'https://example.org')
        url = 'https://en.wikipedia.org/wiki/Fedora_(operating_system)'
        self.assertEqual(web_link_at(f'See {url}.', 10), url)
        self.assertEqual(web_link_at(f'[Fedora]({url})', 3), url)
        self.assertEqual(web_link_at('Visit www.fedoraproject.org.', 10),
                         'https://www.fedoraproject.org')


if __name__ == '__main__':
    unittest.main()
