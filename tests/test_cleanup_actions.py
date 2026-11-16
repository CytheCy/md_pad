"""File cleanup actions apply their shortcuts and undo as single edits."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from main import MainWindow


class CleanupActionTests(unittest.TestCase):
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
        self.editor.setFocus()
        self.app.processEvents()

    def tearDown(self):
        self.editor.document().setModified(False)
        self.window._saved_text = self.editor.toPlainText()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_combined_cleanup_shortcut_and_single_undo(self):
        action = next(a for a in self.window.file_menu.actions()
                      if a.text() == 'Remove Extra Spaces and ↵')
        self.assertEqual(action.shortcut(), QKeySequence('Ctrl+\\'))
        source = '#  \n😀  one  \n\n\ntwo  words'
        self.editor.setPlainText(source)
        QTest.keyClick(self.editor, Qt.Key.Key_Backslash, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.editor.toPlainText(), '# \n😀 one\ntwo words')
        self.editor.undo()
        self.assertEqual(self.editor.toPlainText(), source)

    def test_remove_list_markers_shortcut_and_single_undo(self):
        action = next(a for a in self.window.file_menu.actions()
                      if a.text() == 'Remove Bullets and Numbering')
        self.assertEqual(action.shortcut(), QKeySequence('Ctrl+/'))
        source = '- First\n* Second\n+ Third\n01. Fourth\n9) Fifth\n- - -\n```\n- code\n```\nPlain'
        self.editor.setPlainText(source)
        QTest.keyClick(self.editor, Qt.Key.Key_Slash, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.editor.toPlainText(),
                         'First\nSecond\nThird\nFourth\nFifth\n- - -\n```\n- code\n```\nPlain')
        self.editor.undo()
        self.assertEqual(self.editor.toPlainText(), source)


if __name__ == '__main__':
    unittest.main()
