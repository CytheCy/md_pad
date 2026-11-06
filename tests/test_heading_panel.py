"""Heading navigation follows edits without changing the note."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from main import MainWindow


class HeadingPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, cls.temp.name)
        cls.app = QApplication.instance() or QApplication([])

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        QSettings('Pad', 'Pad').clear()
        self.window = MainWindow()
        self.window.show()
        self.editor = self.window.editor
        self.app.processEvents()

    def tearDown(self):
        self.editor.document().setModified(False)
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_threshold_toggle_and_undo(self):
        w = self.window
        self.assertFalse(w.heading_button.isVisible())
        self.editor.setPlainText('# First')
        self.assertFalse(w.heading_panel.isVisible())
        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        self.editor.insertPlainText('\n## Second')
        self.assertTrue(w.heading_panel.isVisible())
        self.assertTrue(w.heading_button.isVisible())
        self.app.processEvents()
        self.assertLess(w.heading_button.x(), w.minimize_button.x())
        QTest.mouseClick(w.heading_button, Qt.MouseButton.LeftButton)
        self.assertEqual(w.heading_panel_state, 'full')
        self.editor.insertPlainText(' changed')
        self.assertTrue(w.heading_panel.isVisible())
        self.assertTrue(w.heading_button.isVisible())
        QTest.mouseClick(w.heading_button, Qt.MouseButton.LeftButton)
        self.assertEqual(w.heading_panel_state, 'closed')
        self.assertFalse(w.heading_panel.isVisible())
        QTest.mouseClick(w.heading_button, Qt.MouseButton.LeftButton)
        self.assertEqual(w.heading_panel_state, 'narrow')
        self.assertTrue(w.heading_panel.isVisible())
        self.editor.selectAll()
        self.editor.insertPlainText('# Only one')
        self.assertFalse(w.heading_panel.isVisible())
        self.assertFalse(w.heading_button.isVisible())
        self.editor.undo()
        self.assertTrue(w.heading_panel.isVisible())

    def test_click_after_edit_navigates_unicode_duplicate_heading(self):
        w = self.window
        self.editor.setPlainText('# Same\n' + '😀 body\n' * 70 + '### Same ###\nEnd')
        self.editor.moveCursor(QTextCursor.MoveOperation.Start)
        self.editor.insertPlainText('😀 inserted\n')
        self.app.processEvents()
        document = self.editor.document()
        before = (self.editor.toPlainText(), document.isModified(), document.availableUndoSteps())
        item = w.heading_list.item(1)
        self.assertEqual(item.text(), 'Sam')
        QTest.mouseClick(w.heading_list.viewport(), Qt.MouseButton.LeftButton,
                         pos=w.heading_list.visualItemRect(item).center())
        self.app.processEvents()
        self.assertEqual(self.editor.textCursor().block().text(), '### Same ###')
        self.assertTrue(self.editor.viewport().rect().intersects(self.editor.cursorRect()))
        self.assertTrue(self.editor.hasFocus())
        self.assertEqual((self.editor.toPlainText(), document.isModified(), document.availableUndoSteps()), before)

    def test_code_plain_text_and_file_switching(self):
        w = self.window
        source = '# First\n```md\n## Code\n```\n~~~\n# Also code\n~~~\n###### Last\n####### Invalid'
        with tempfile.TemporaryDirectory() as directory:
            md = Path(directory) / 'note.md'
            txt = Path(directory) / 'note.txt'
            md.write_text(source)
            txt.write_text(source)
            w.open_file(md)
            self.assertEqual(w.heading_list.count(), 2)
            self.assertTrue(w.heading_panel.isVisible())
            w.heading_state_actions['closed'].trigger()
            self.assertFalse(w.heading_panel.isVisible())
            w.open_file(md)
            self.assertFalse(w.heading_panel.isVisible())
            w.open_file(txt)
            self.assertFalse(w.heading_button.isVisible())
            self.assertFalse(w.heading_panel.isVisible())
            w.open_file(md)
            w.new_file()
            self.assertFalse(w.heading_button.isVisible())
            self.assertEqual(w.heading_list.count(), 0)

    def test_panel_state_and_full_width_survive_reopening(self):
        self.editor.setPlainText('# First\n## Second')
        self.app.processEvents()
        self.window.heading_state_actions['full'].trigger()
        splitter = self.window.content_splitter
        splitter.moveSplitter(splitter.width() - 366, 1)
        self.app.processEvents()
        saved_width = splitter.sizes()[1]
        self.assertGreater(saved_width, 240)
        self.assertEqual(QSettings('Pad', 'Pad').value('heading_panel_width', type=int), saved_width)

        self.window.heading_state_actions['closed'].trigger()
        self.assertFalse(self.window.heading_panel.isVisible())
        self.editor.document().setModified(False)
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

        self.window = MainWindow()
        self.window.show()
        self.editor = self.window.editor
        self.editor.setPlainText('# First\n## Second')
        self.app.processEvents()
        self.assertEqual(self.window.heading_panel_state, 'closed')
        self.assertFalse(self.window.heading_panel.isVisible())
        self.window.heading_state_actions['full'].trigger()
        self.app.processEvents()
        self.assertEqual(self.window.content_splitter.sizes()[1], saved_width)

    def test_button_cycles_states_without_hover_expansion(self):
        w = self.window
        self.editor.setPlainText('# Longer first heading\n### Another heading')
        self.app.processEvents()
        self.assertEqual(w.heading_list.textElideMode(), Qt.TextElideMode.ElideNone)
        compact_width = w.content_splitter.sizes()[1]
        self.assertEqual([w.heading_list.item(i).text() for i in range(2)], ['Lon', 'Ano'])
        self.assertLess(compact_width, 100)

        QTest.mouseMove(w.heading_panel, w.heading_panel.rect().center())
        self.app.processEvents()
        self.assertEqual([w.heading_list.item(i).text() for i in range(2)], ['Lon', 'Ano'])
        self.assertEqual(w.content_splitter.sizes()[1], compact_width)

        w.heading_button.click()
        self.app.processEvents()
        self.assertEqual([w.heading_list.item(i).text() for i in range(2)],
                         ['Longer first heading', '    Another heading'])
        expanded_width = w.content_splitter.sizes()[1]
        self.assertGreater(expanded_width, compact_width)

        w.content_splitter.moveSplitter(w.content_splitter.width() - 300, 1)
        self.app.processEvents()
        expanded_width = w.content_splitter.sizes()[1]
        self.assertGreater(expanded_width, compact_width)

        QTest.mouseMove(self.editor.viewport(), self.editor.viewport().rect().center())
        QTest.qWait(120)
        self.assertEqual(w.content_splitter.sizes()[1], expanded_width)
        w.heading_button.click()
        self.assertEqual(w.heading_panel_state, 'closed')
        self.assertFalse(w.heading_panel.isVisible())
        w.heading_button.click()
        self.assertEqual([w.heading_list.item(i).text() for i in range(2)], ['Lon', 'Ano'])
        self.assertEqual(w.content_splitter.sizes()[1], compact_width)
        self.assertTrue(w.heading_state_actions['narrow'].isChecked())

    def test_clicking_opened_file_does_not_request_save(self):
        source = '# First\nBody text\n## Second\nMore body\n'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'note.md'
            path.write_text(source)
            self.assertTrue(self.window.open_file(path))
            self.app.processEvents()
            document = self.editor.document()
            self.assertFalse(document.isModified())

            for line in (0, 1, 2, 3):
                cursor = QTextCursor(document.findBlockByNumber(line))
                cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
                QTest.mouseClick(self.editor.viewport(), Qt.MouseButton.LeftButton,
                                 pos=self.editor.cursorRect(cursor).center())
                self.app.processEvents()
                self.assertFalse(document.isModified())
                self.assertFalse(self.window.windowTitle().startswith('*'))

            self.assertEqual(self.editor.toPlainText(), source)
            self.assertEqual(document.availableUndoSteps(), 0)
            with patch.object(QMessageBox, 'question') as question:
                self.assertTrue(self.window.close())
                question.assert_not_called()
