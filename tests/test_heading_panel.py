"""Heading navigation follows edits without changing the note."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

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
        self.editor.insertPlainText(' changed')
        self.assertFalse(w.heading_panel.isVisible())
        self.assertTrue(w.heading_button.isVisible())
        QTest.mouseClick(w.heading_button, Qt.MouseButton.LeftButton)
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
        self.assertEqual(item.text().strip(), 'Same')
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
            w.heading_button.click()
            w.open_file(md)
            self.assertTrue(w.heading_panel.isVisible())
            w.open_file(txt)
            self.assertFalse(w.heading_button.isVisible())
            self.assertFalse(w.heading_panel.isVisible())
            w.open_file(md)
            w.new_file()
            self.assertFalse(w.heading_button.isVisible())
            self.assertEqual(w.heading_list.count(), 0)
