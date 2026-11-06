"""Fenced code panels render without changing source and copy only code text."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QToolTip

from main import MarkdownHighlighter, NoteEditor
from themes import THEMES


class CodePanelTests(unittest.TestCase):
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
        QToolTip.hideText()
        self.editor.close()
        self.editor.deleteLater()
        self.app.processEvents()

    def test_panel_copy_and_plain_text_mode(self):
        source = 'Before\n```python\nAll\nx = 1\n```\nAfter'
        self.editor.setPlainText(source)
        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        self.app.processEvents()
        document = self.editor.document()
        document.setModified(False)
        before = document.availableUndoSteps()

        self.assertEqual(len(self.editor.code_panels), 1)
        self.assertEqual(len(self.editor._code_selections), 4)
        start, end = self.editor.code_panels[0]
        panel = self.editor.code_panel_rect(start, end)
        self.assertGreater(panel.width(), 300)
        self.assertGreater(panel.height(), 50)
        icon = self.editor.code_copy_rect(panel)
        icon_pixel = (int(icon.left() + 7), int(icon.top() + 10))
        before_hover = self.editor.viewport().grab().toImage().pixelColor(*icon_pixel)
        QTest.mouseMove(self.editor.viewport(), panel.center().toPoint())
        self.assertEqual(self.editor._hovered_code_panel, (start, end))
        after_hover = self.editor.viewport().grab().toImage().pixelColor(*icon_pixel)
        self.assertNotEqual(before_hover, after_hover)
        QTest.mouseClick(self.editor.viewport(), Qt.MouseButton.LeftButton,
                         pos=icon.center().toPoint())
        self.assertEqual(self.app.clipboard().text(), 'All\nx = 1')
        self.assertEqual(QToolTip.text(), 'Copied')
        QTest.mouseMove(self.editor.viewport(), self.editor.viewport().rect().bottomRight())
        self.assertIsNone(self.editor._hovered_code_panel)
        self.assertEqual(self.editor.viewport().grab().toImage().pixelColor(*icon_pixel),
                         before_hover)
        self.assertEqual(self.editor.toPlainText(), source)
        self.assertFalse(document.isModified())
        self.assertEqual(document.availableUndoSteps(), before)

        self.highlighter.enabled = False
        self.highlighter.rehighlight()
        self.editor.update_code_panels()
        self.assertEqual(self.editor.code_panels, [])
        self.assertEqual(self.editor._code_selections, [])

    def test_wrapped_code_rows_keep_panel_background_and_copy_source_line(self):
        code = 'John turns and walks down the hall. We are changing the house battery.'
        self.editor.resize(350, 400)
        self.editor.setPlainText(f'Before\n```\n{code}\n```\nAfter')
        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        self.app.processEvents()
        block = self.editor.document().findBlockByNumber(2)
        layout = block.layout()
        self.assertGreater(layout.lineCount(), 1)
        self.assertEqual(len(self.editor._code_selections), layout.lineCount() + 2)

        panel_color = THEMES['catppuccin-mocha']['md_code_background'].upper()
        image = self.editor.viewport().grab().toImage()
        x = self.editor.viewport().width() - 50
        for index in range(layout.lineCount()):
            line = layout.lineAt(index)
            cursor = QTextCursor(block)
            cursor.setPosition(block.position() + line.textStart() +
                               (1 if line.textLength() > 1 else 0))
            y = self.editor.cursorRect(cursor).center().y()
            self.assertEqual(image.pixelColor(x, y).name().upper(), panel_color)

        start, end = self.editor.code_panels[0]
        icon = self.editor.code_copy_rect(self.editor.code_panel_rect(start, end))
        QTest.mouseClick(self.editor.viewport(), Qt.MouseButton.LeftButton,
                         pos=icon.center().toPoint())
        self.assertEqual(self.app.clipboard().text(), code)


if __name__ == '__main__':
    unittest.main()
