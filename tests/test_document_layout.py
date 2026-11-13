"""Long notes must retain visible paragraphs after highlighting and font changes."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPoint, QPointF, QSettings, Qt, QTimer
from PySide6.QtGui import QTextCursor, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QSpinBox

from main import MainWindow


class DocumentLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'long-note.md'
        self.source = '# Title\n' + '\n'.join(
            'A paragraph with several words to wrap across the page. ' * (1 + i % 10)
            for i in range(125)) + '\n## End\nFinal paragraph.'
        self.path.write_text(self.source)
        settings = QSettings(str(Path(self.temp.name) / 'settings.ini'), QSettings.Format.IniFormat)
        with patch('main.QSettings', return_value=settings):
            self.window = MainWindow(self.path)
        self.window.show()
        QTest.qWait(350)

    def tearDown(self):
        self.window.editor.document().setModified(False)
        self.window._saved_text = self.window.editor.toPlainText()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def assert_all_paragraphs_visible(self):
        editor = self.window.editor
        document = editor.document()
        block = document.firstBlock()
        while block.isValid():
            rect = document.documentLayout().blockBoundingRect(block)
            self.assertGreater(rect.height(), 0, f'Collapsed paragraph {block.blockNumber()}')
            self.assertGreater(block.layout().lineCount(), 0)
            block = block.next()
        editor.moveCursor(QTextCursor.MoveOperation.End)
        editor.ensureCursorVisible()
        self.app.processEvents()
        self.assertTrue(editor.viewport().rect().intersects(editor.cursorRect()))
        self.assertEqual(editor.toPlainText(), self.source)
        self.assertEqual(self.path.read_text(), self.source)
        self.assertFalse(document.isModified())
        self.assertFalse(document.isUndoAvailable())

    def test_open_and_delayed_highlighting_keep_every_paragraph_visible(self):
        self.assert_all_paragraphs_visible()
        self.window.editor.moveCursor(QTextCursor.MoveOperation.Start)
        self.window.editor.schedule_code_panel_update()
        QTest.qWait(350)
        self.assert_all_paragraphs_visible()

    def test_trackpad_scrolls_while_markdown_source_is_visible(self):
        editor = self.window.editor
        viewport = editor.viewport()
        point = QPoint(100, 50)
        QTest.mouseClick(viewport, Qt.MouseButton.LeftButton, pos=point)
        self.assertEqual(editor.textCursor().blockNumber(), 0)
        bar = editor.verticalScrollBar()
        self.assertGreater(bar.maximum(), 0)
        before = bar.value()
        event = QWheelEvent(QPointF(point), QPointF(viewport.mapToGlobal(point)),
                            QPoint(0, -24), QPoint(0, 0), Qt.MouseButton.NoButton,
                            Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.ScrollUpdate, False)
        QApplication.sendEvent(viewport, event)
        self.assertTrue(event.isAccepted())
        self.assertEqual(bar.value(), before + 24)
        wheel = QWheelEvent(QPointF(point), QPointF(viewport.mapToGlobal(point)),
                            QPoint(0, 0), QPoint(0, -120), Qt.MouseButton.NoButton,
                            Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.NoScrollPhase, False)
        QApplication.sendEvent(viewport, wheel)
        self.assertTrue(wheel.isAccepted())
        self.assertGreater(bar.value(), before + 24)
        self.assertEqual(editor.toPlainText(), self.source)
        self.assertFalse(editor.document().isModified())

    def test_mouse_wheel_and_trackpad_scroll_over_both_page_margins(self):
        editor = self.window.editor
        self.window.set_max_page_width(500)
        self.app.processEvents()
        viewport = editor.viewport()
        margins = (QPoint(viewport.geometry().left() // 2, 100),
                   QPoint((viewport.geometry().right() + editor.width()) // 2, 100))
        bar = editor.verticalScrollBar()
        for dismissed in (False, True):
            for point in margins:
                for pixels, angle in ((QPoint(0, -24), QPoint()),
                                      (QPoint(), QPoint(0, -120)),
                                      (QPoint(0, 24), QPoint()),
                                      (QPoint(), QPoint(0, 120))):
                    with self.subTest(dismissed=dismissed, point=point,
                                      pixels=pixels, angle=angle):
                        editor.setFocus()
                        if dismissed:
                            QTest.mouseClick(editor, Qt.MouseButton.LeftButton, pos=point)
                        position = editor.textCursor().position()
                        active_block = editor.highlighter.active_block
                        bar.setValue(bar.maximum() // 2)
                        before = bar.value()
                        event = QWheelEvent(
                            QPointF(point), QPointF(editor.mapToGlobal(point)),
                            pixels, angle, Qt.MouseButton.NoButton,
                            Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.NoScrollPhase, False)
                        QApplication.sendEvent(editor, event)
                        self.assertTrue(event.isAccepted())
                        if pixels.y():
                            self.assertEqual(bar.value(), before - pixels.y())
                        elif angle.y() < 0:
                            self.assertGreater(bar.value(), before)
                        else:
                            self.assertLess(bar.value(), before)
                        self.assertEqual(editor.hasFocus(), not dismissed)
                        self.assertEqual(editor.highlighter.active_block, active_block)
                        self.assertEqual(editor.textCursor().position(), position)
        self.assertEqual(editor.toPlainText(), self.source)
        self.assertFalse(editor.document().isModified())

    def test_clicking_off_page_dismisses_cursor_and_clicking_text_resumes_editing(self):
        editor = self.window.editor
        self.window.set_max_page_width(500)
        self.app.processEvents()
        viewport = editor.viewport()
        point = editor.cursorRect(QTextCursor(editor.document())).center()
        QTest.mouseClick(viewport, Qt.MouseButton.LeftButton, pos=point)
        self.assertTrue(editor.hasFocus())

        for widget, outside in (
                (editor, QPoint(editor.viewport().geometry().left() // 2,
                                editor.height() // 2)),
                (self.window.count_label, self.window.count_label.rect().center())):
            with self.subTest(widget=widget):
                editor.selectAll()
                position = editor.textCursor().position()
                QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=outside)
                self.assertFalse(editor.hasFocus())
                self.assertFalse(editor.textCursor().hasSelection())
                self.assertEqual(editor.textCursor().position(), position)
                self.assertEqual(editor.toPlainText(), self.source)
                self.assertFalse(editor.document().isModified())

                editor.moveCursor(QTextCursor.MoveOperation.Start)
                QTest.mouseClick(viewport, Qt.MouseButton.LeftButton, pos=point)
                self.assertTrue(editor.hasFocus())

        position = editor.textCursor().position()
        QTest.keyClicks(viewport, 'Hello ')
        self.assertEqual(editor.toPlainText(),
                         self.source[:position] + 'Hello ' + self.source[position:])

    def test_clicking_page_margins_restores_table_and_other_markdown(self):
        editor = self.window.editor
        source = ('| Name | Price |\n|:---|---:|\n| One | $1 |\n'
                  '# Heading\n```python\nx = 1\n```\nAfter')
        editor.setPlainText(source)
        editor.moveCursor(QTextCursor.MoveOperation.End)
        self.window.set_max_page_width(500)
        self.app.processEvents()
        document = editor.document()
        document.setModified(False)
        undo_steps = document.availableUndoSteps()
        viewport = editor.viewport()
        margins = (QPoint(viewport.geometry().left() // 2, 100),
                   QPoint((viewport.geometry().right() + editor.width()) // 2, 100))

        for line in (0, 1, 2, 3, 4, 5):
            for margin in margins:
                with self.subTest(line=line, margin=margin):
                    block = document.findBlockByNumber(line)
                    point = editor.cursorRect(QTextCursor(block)).center()
                    QTest.mouseClick(viewport, Qt.MouseButton.LeftButton, pos=point)
                    self.assertEqual(editor.highlighter.active_block, block)
                    if line < 3:
                        self.assertEqual(editor._table_edit_position, block.position())
                    QTest.mouseClick(editor, Qt.MouseButton.LeftButton, pos=margin)
                    self.app.processEvents()
                    self.assertFalse(editor.hasFocus())
                    self.assertIsNone(editor.highlighter.active_block)
                    self.assertIsNone(editor.highlighter.active_code_panel)
                    self.assertIsNone(editor._table_edit_position)
                    if line < 3:
                        self.assertTrue(all(item.format.foreground().color().alpha() == 0
                                            for item in block.layout().formats()))
                    self.assertEqual(editor.toPlainText(), source)
                    self.assertFalse(document.isModified())
                    self.assertEqual(document.availableUndoSteps(), undo_steps)
        self.assertFalse(viewport.grab().isNull())

    def test_font_dialog_keeps_every_paragraph_and_the_end_accessible(self):
        for points in (14, 18, 10):
            with self.subTest(points=points):
                def change_size():
                    dialog = self.app.activeModalWidget()
                    dialog.findChild(QSpinBox).setValue(points)
                    QTimer.singleShot(350, dialog.close)
                QTimer.singleShot(0, change_size)
                self.window.show_font_size()
                self.assertEqual(self.window.font_size, points)
                self.assert_all_paragraphs_visible()

    def test_font_change_centers_cursor_in_long_note(self):
        editor = self.window.editor
        cursor = QTextCursor(editor.document().findBlockByNumber(65))
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        editor.setTextCursor(cursor)
        editor.ensureCursorVisible()

        for points in (24, 10, 18):
            with self.subTest(points=points):
                self.window.set_font_size(points)
                QTest.qWait(350)
                self.assertEqual(editor.textCursor().position(), cursor.position())
                self.assertLessEqual(
                    abs(editor.cursorRect().center().y() - editor.viewport().rect().center().y()),
                    editor.cursorRect().height())


if __name__ == '__main__':
    unittest.main()
