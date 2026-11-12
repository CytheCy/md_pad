"""Find highlights source text without changing the document."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QToolButton

from main import MainWindow


class FindTests(unittest.TestCase):
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
        self.window._saved_text = self.editor.toPlainText()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_menu_find_highlights_counts_and_wraps(self):
        self.editor.setPlainText('One one\n😀 ONE')
        self.editor.document().setModified(False)
        self.editor.document().clearUndoRedoStacks()
        next(action for action in self.window.menuBar().actions()[0].menu().actions()
             if action.text() == 'Find').trigger()
        self.assertTrue(self.window.find_footer.isVisible())
        self.assertTrue(self.window.find_input.hasFocus())
        self.window.find_input.setText('one')
        self.assertEqual(self.window.find_matches, [(0, 3), (4, 7), (11, 14)])
        self.assertEqual(self.window.find_count.text(), '1 of 3')
        self.assertEqual(len(self.editor._find_selections), 3)
        QTest.mouseClick(self.window.find_previous, Qt.MouseButton.LeftButton)
        self.assertEqual(self.window.find_count.text(), '3 of 3')
        self.assertEqual(self.editor.textCursor().position(), 11)
        QTest.mouseClick(self.window.find_next, Qt.MouseButton.LeftButton)
        self.assertEqual(self.window.find_count.text(), '1 of 3')
        self.assertFalse(self.editor.document().isModified())
        self.assertEqual(self.editor.document().availableUndoSteps(), 0)

    def test_edit_updates_matches_and_escape_closes(self):
        self.editor.setPlainText('cat cat')
        self.window.open_find()
        self.window.find_input.setText('cat')
        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        self.editor.insertPlainText(' cat')
        self.assertEqual(self.window.find_count.text(), '3 of 3')
        self.assertEqual(len(self.editor._find_selections), 3)
        self.window.find_input.setText('missing')
        self.assertEqual(self.window.find_count.text(), '0 matches')
        self.assertFalse(self.window.find_next.isEnabled())
        QTest.keyClick(self.window.find_input, Qt.Key.Key_Escape)
        self.assertFalse(self.window.find_footer.isVisible())
        self.assertEqual(self.editor._find_selections, [])

    def test_case_and_whole_word_buttons_update_results(self):
        self.editor.setPlainText('May may MAY fall fallow rainfall fall.')
        self.editor.document().setModified(False)
        self.window.open_find()
        self.window.find_input.setText('May')
        self.assertEqual(len(self.window.find_matches), 3)
        QTest.mouseClick(self.window.find_match_case, Qt.MouseButton.LeftButton)
        self.assertTrue(self.window.find_match_case.isChecked())
        self.assertEqual(self.window.find_matches, [(0, 3)])
        self.assertEqual(self.window.find_count.text(), '1 of 1')
        QTest.mouseClick(self.window.find_match_case, Qt.MouseButton.LeftButton)
        self.assertEqual(len(self.window.find_matches), 3)

        self.window.find_input.setText('fall')
        self.assertEqual(len(self.window.find_matches), 4)
        QTest.mouseClick(self.window.find_whole_word, Qt.MouseButton.LeftButton)
        self.assertTrue(self.window.find_whole_word.isChecked())
        self.assertEqual(self.window.find_matches, [(12, 16), (33, 37)])
        self.assertEqual(self.window.find_count.text(), '1 of 2')
        QTest.mouseClick(self.window.find_whole_word, Qt.MouseButton.LeftButton)
        self.assertEqual(len(self.window.find_matches), 4)
        self.assertFalse(self.editor.document().isModified())

    def test_menu_and_shortcut_toggle_and_restore_query(self):
        self.editor.setPlainText('cat cat')
        find_action = next(action for action in self.window.menuBar().actions()[0].menu().actions()
                           if action.text() == 'Find')
        find_action.trigger()
        self.window.find_input.setText('cat')
        self.assertEqual(len(self.editor._find_selections), 2)

        find_action.trigger()
        self.assertFalse(self.window.find_footer.isVisible())
        self.assertEqual(self.window.find_input.text(), 'cat')
        self.assertEqual(self.window.find_matches, [])
        self.assertEqual(self.editor._find_selections, [])

        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        self.editor.insertPlainText(' cat')
        QTest.keyClick(self.editor, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(self.window.find_footer.isVisible())
        self.assertEqual(self.window.find_input.text(), 'cat')
        self.assertEqual(len(self.editor._find_selections), 3)

        QTest.keyClick(self.window.find_input, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
        self.assertFalse(self.window.find_footer.isVisible())
        self.assertEqual(self.editor._find_selections, [])
        find_action.trigger()
        self.window.find_input.clear()
        self.assertEqual(self.editor._find_selections, [])
        find_action.trigger()
        find_action.trigger()
        self.assertEqual(self.window.find_input.text(), '')
        self.assertEqual(self.editor._find_selections, [])

    def test_clear_icon_empties_query_and_highlights(self):
        self.editor.setPlainText('rain rain')
        self.window.open_find()
        self.window.find_input.setText('rain')
        self.app.processEvents()
        clear_button = self.window.find_input.findChild(QToolButton)
        self.assertIsNotNone(clear_button)
        self.assertTrue(clear_button.isVisible())
        QTest.mouseClick(clear_button, Qt.MouseButton.LeftButton)
        self.assertEqual(self.window.find_input.text(), '')
        self.assertEqual(self.window.find_count.text(), '0 matches')
        self.assertEqual(self.editor._find_selections, [])
        self.window.find_input.setText('rain')
        self.assertEqual(len(self.editor._find_selections), 2)

    def test_replace_footer_shortcut_and_switching(self):
        self.editor.setPlainText('cat cat')
        QTest.keyClick(self.editor, Qt.Key.Key_R, Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(self.window.replace_footer.isVisible())
        self.window.open_replace()
        self.window.open_find()
        self.window.find_input.setText('cat')
        QTest.keyClick(self.window.find_input, Qt.Key.Key_R, Qt.KeyboardModifier.ControlModifier)
        self.assertFalse(self.window.find_footer.isVisible())
        self.assertTrue(self.window.replace_footer.isVisible())
        self.window.replace_search_input.setText('cat')
        self.assertEqual(self.window.replace_count.text(), '1 of 2')
        self.assertEqual(len(self.editor._find_selections), 2)
        QTest.keyClick(self.window.replace_search_input, Qt.Key.Key_F,
                       Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(self.window.find_footer.isVisible())
        self.assertFalse(self.window.replace_footer.isVisible())
        self.assertEqual(self.window.find_input.text(), 'cat')
        self.assertEqual(len(self.editor._find_selections), 2)
        self.window.open_replace()
        self.assertEqual(self.window.replace_search_input.text(), 'cat')
        self.window.open_replace()
        self.assertFalse(self.window.replace_footer.isVisible())
        self.assertEqual(self.editor._find_selections, [])

    def test_replace_current_and_all_respect_options_and_undo(self):
        original = 'May may fall fallow fall'
        self.editor.setPlainText(original)
        self.editor.document().setModified(False)
        self.editor.document().clearUndoRedoStacks()
        self.window.open_replace()
        self.window.replace_search_input.setText('May')
        self.window.replace_match_case.click()
        self.assertEqual(self.window.find_matches, [(0, 3)])
        self.window.replace_input.setText('June')
        QTest.mouseClick(self.window.replace_next_button, Qt.MouseButton.LeftButton)
        self.assertEqual(self.editor.toPlainText(), 'June may fall fallow fall')
        self.editor.undo()
        self.assertEqual(self.editor.toPlainText(), original)

        self.window.replace_search_input.setText('fall')
        self.window.replace_whole_word.click()
        self.assertEqual(len(self.window.find_matches), 2)
        self.window.replace_input.setText('drop')
        QTest.mouseClick(self.window.replace_all_button, Qt.MouseButton.LeftButton)
        self.assertEqual(self.editor.toPlainText(), 'May may drop fallow drop')
        self.assertEqual(self.window.replace_count.text(), '0 matches')
        self.editor.undo()
        self.assertEqual(self.editor.toPlainText(), original)

    def test_replace_can_delete_and_clear_search(self):
        self.editor.setPlainText('one two one')
        self.window.open_replace()
        self.window.replace_search_input.setText('one')
        self.window.replace_input.clear()
        self.window.replace_all_button.click()
        self.assertEqual(self.editor.toPlainText(), ' two ')
        self.window.replace_search_input.setText('two')
        self.app.processEvents()
        clear_button = self.window.replace_search_input.findChild(QToolButton)
        QTest.mouseClick(clear_button, Qt.MouseButton.LeftButton)
        self.assertEqual(self.window.replace_search_input.text(), '')
        self.assertEqual(self.editor._find_selections, [])

    def test_replace_current_advances_and_wraps(self):
        self.editor.setPlainText('cat cat cat')
        self.window.open_replace()
        self.window.replace_search_input.setText('cat')
        self.window.replace_input.setText('dog')
        self.window.replace_next_button.click()
        self.assertEqual(self.editor.toPlainText(), 'dog cat cat')
        self.assertEqual(self.window.replace_count.text(), '1 of 2')
        self.assertEqual(self.editor.textCursor().position(), 4)
        self.window.replace_next_button.click()
        self.assertEqual(self.editor.toPlainText(), 'dog dog cat')
        self.assertEqual(self.editor.textCursor().position(), 8)
        self.window.replace_next_button.click()
        self.assertEqual(self.editor.toPlainText(), 'dog dog dog')
        self.assertEqual(self.window.replace_count.text(), '0 matches')

    def test_replace_controls_fit_on_one_line_at_minimum_width(self):
        self.window.resize(640, 440)
        self.window.open_replace()
        self.app.processEvents()
        controls = [self.window.replace_search_input, self.window.replace_match_case,
                    self.window.replace_whole_word, self.window.replace_count,
                    self.window.replace_previous, self.window.replace_next,
                    self.window.replace_input, self.window.replace_next_button,
                    self.window.replace_all_button]
        positions = [control.mapTo(self.window.replace_footer, control.rect().center())
                     for control in controls]
        self.assertLess(max(point.y() for point in positions) - min(point.y() for point in positions), 8)
        self.assertGreaterEqual(self.window.replace_search_input.width(), 80)
        self.assertGreaterEqual(self.window.replace_input.width(), 80)
        self.assertLess(positions[-1].x(), self.window.replace_footer.width())


if __name__ == '__main__':
    unittest.main()
