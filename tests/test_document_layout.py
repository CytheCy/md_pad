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
