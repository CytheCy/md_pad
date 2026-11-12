"""Spelling integration and document preservation tests."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import unittest

from PySide6.QtCore import QSettings
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication

from main import MainWindow
from spelling import prose_words


class SpellingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.temp = tempfile.TemporaryDirectory()
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, cls.temp.name)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        QSettings('Pad', 'Pad').clear()
        self.window = MainWindow()
        self.editor = self.window.editor
        self.spelling = self.editor.spelling

    def tearDown(self):
        self.editor.document().setModified(False)
        self.window._saved_text = self.editor.toPlainText()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def marked(self):
        self.spelling.refresh()
        return [s.cursor.selectedText() for s in self.editor.extraSelections()]

    def test_unicode_and_formatting_preservation(self):
        self.editor.setPlainText('😀 **speling** hello')
        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        self.editor.insertPlainText(' world')
        doc = self.editor.document()
        before = (self.editor.toPlainText(), doc.availableUndoSteps(), doc.isModified(), self.editor.textCursor().position())
        self.assertEqual(self.marked(), ['speling'])
        for theme in ('tokyo-night', 'everforest-dark'):
            self.window.set_theme(theme)
            self.assertEqual(self.marked(), ['speling'])
        after = (self.editor.toPlainText(), doc.availableUndoSteps(), doc.isModified(), self.editor.textCursor().position())
        self.assertEqual(before, after)

    def test_markdown_exclusions_and_plain_text(self):
        source = 'speling `typpo` [helo](typpo) https://typpo.test\n```python\ntyppo\n```\n    typpo\n'
        self.editor.setPlainText(source)
        self.assertEqual(self.marked(), ['speling', 'helo'])
        self.window.highlighter.enabled = False
        self.assertIn('typpo', self.marked())
        words = [word for _, _, word in prose_words("don't don’t user_name abc123 name@example.test")]
        self.assertEqual(words, ["don't", 'don’t'])

    def test_suggestion_replacement_is_one_undo_step(self):
        self.editor.setPlainText('😀 Speling and speling')
        self.assertIn('Spelling', self.spelling.suggestions('Speling'))
        self.spelling.refresh()
        selections = self.editor.extraSelections()
        cursor = QTextCursor(selections[0].cursor)
        self.spelling.replace(cursor, 'Spelling')
        self.assertEqual(self.editor.toPlainText(), '😀 Spelling and speling')
        self.editor.undo()
        self.assertEqual(self.editor.toPlainText(), '😀 Speling and speling')

    def test_personal_dictionary_ignore_and_toggle_persist(self):
        self.editor.setPlainText('speling typpo')
        self.spelling.accept_word('speling')
        self.spelling.accept_word('typpo', permanent=True)
        self.assertEqual(self.marked(), [])
        self.window.spell_check_action.setChecked(False)
        restored = MainWindow()
        try:
            self.assertFalse(restored.editor.spelling.enabled)
            self.assertIn('typpo', restored.editor.spelling.personal)
            self.assertNotIn('speling', restored.editor.spelling.ignored)
        finally:
            restored.close()
            restored.deleteLater()
        self.window.spell_check_action.setChecked(True)
        self.editor.setPlainText('helo')
        self.assertEqual(self.marked(), ['helo'])
        self.window.spell_check_action.setChecked(False)
        self.assertEqual(self.editor.extraSelections(), [])

    def test_context_menu_corrects_clicked_occurrence(self):
        self.window.show()
        self.editor.setPlainText('speling and speling')
        self.app.processEvents()
        cursor = QTextCursor(self.editor.document())
        cursor.setPosition(15)
        menu = self.spelling.context_menu(self.editor.cursorRect(cursor).center())
        try:
            action = next(a for a in menu.actions() if a.text() == 'spelling')
            action.trigger()
            self.assertEqual(self.editor.toPlainText(), 'speling and spelling')
        finally:
            menu.deleteLater()


if __name__ == '__main__':
    unittest.main()
