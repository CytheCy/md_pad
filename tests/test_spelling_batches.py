"""Spelling remains local, interruptible, and cached while preserving exclusions."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QSettings
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication

from main import MarkdownHighlighter, NoteEditor
from spelling import Spelling, prose_words
from themes import THEMES


class SpellingBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.editor = NoteEditor()
        self.highlighter = MarkdownHighlighter(
            self.editor.document(), THEMES['catppuccin-mocha'], self.editor)
        settings = QSettings(str(Path(self.temp.name) / 'settings.ini'), QSettings.Format.IniFormat)
        self.spelling = Spelling(self.editor, settings, self.highlighter)
        self.spelling.refresh()

    def tearDown(self):
        self.spelling.set_enabled(False)
        self.editor.close()
        self.editor.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def finish(self):
        self.spelling.refresh()
        for _ in range(10000):
            if self.spelling._pending_start is None and self.spelling._job is None:
                return
            self.spelling.process_batch()
        self.fail('Spelling queue did not finish')

    def marked(self):
        return [s.cursor.selectedText() for s in self.editor.extraSelections()]

    def test_initial_scan_yields_and_dictionary_checks_repeated_words_once(self):
        self.editor.setPlainText('\n'.join('hello speling' for _ in range(2000)))
        s = self.spelling
        with patch.object(type(s.dictionary), 'unknown', wraps=s.dictionary.unknown) as lookup:
            with patch.object(self.editor, 'toPlainText', side_effect=AssertionError('Whole-document copy')):
                s.refresh()
                self.assertIsNotNone(s._pending_start)
                self.assertTrue(s.batch_timer.isActive())
                self.assertLess(len(self.editor.extraSelections()), 2000)
                self.finish()
            self.assertEqual(lookup.call_count, 2)
        self.assertEqual(self.marked(), ['speling'] * 2000)
        self.assertFalse(s.batch_timer.isActive())

    def test_local_edit_checks_one_paragraph_and_reuses_other_underlines(self):
        self.editor.setPlainText('hello speling\n' * 1000)
        self.finish()
        unaffected = self.editor.extraSelections()[-1]
        with patch.object(self.spelling, 'check_block', wraps=self.spelling.check_block) as check:
            self.editor.insertPlainText('x')
            self.finish()
            self.assertEqual(check.call_count, 1)
        self.assertIs(self.editor.extraSelections()[-1], unaffected)

    def test_long_paragraph_yields_and_replaced_document_discards_partial_results(self):
        self.editor.setPlainText('speling ' * 3000)
        s = self.spelling
        with patch.object(s, 'known', wraps=s.known) as known:
            s.refresh()
            self.assertLessEqual(known.call_count, s.BATCH_STEPS)
        self.assertTrue(s.batch_timer.isActive())
        self.editor.setPlainText('hello')
        self.finish()
        self.assertEqual(self.marked(), [])
        self.assertFalse(s.batch_timer.isActive())

    def test_fence_edit_propagates_and_undo_restores_exclusions(self):
        source = 'speling\n````python\ntyppo\n```\nhelo\n````\nwrng\nTail'
        self.editor.setPlainText(source)
        self.finish()
        self.assertEqual(self.marked(), ['speling', 'wrng'])
        cursor = QTextCursor(self.editor.document().findBlockByNumber(1))
        cursor.select(QTextCursor.SelectionType.LineUnderCursor)
        cursor.insertText('hello')
        self.finish()
        expected = [word for _, _, word in prose_words(self.editor.toPlainText())
                    if not self.spelling.known(self.spelling.normalize(word))]
        self.assertEqual(self.marked(), expected)
        self.editor.undo()
        self.finish()
        self.assertEqual(self.marked(), ['speling', 'wrng'])

    def test_edit_during_fence_propagation_keeps_unfinished_range(self):
        self.editor.setPlainText('hello\n```\n' + 'speling\n' * 200 + '```\nhelo')
        self.finish()
        cursor = QTextCursor(self.editor.document().findBlockByNumber(1))
        cursor.select(QTextCursor.SelectionType.LineUnderCursor)
        cursor.insertText('hello')
        self.spelling.refresh()
        self.assertTrue(self.spelling.batch_timer.isActive())
        cursor = QTextCursor(self.editor.document().firstBlock())
        cursor.insertText('world ')
        self.finish()
        self.assertEqual(self.marked(), ['speling'] * 200)

    def test_disable_and_ignore_cancel_uncommitted_results(self):
        self.editor.setPlainText('speling ' * 1000)
        self.spelling.refresh()
        self.spelling.accept_word('speling')
        self.finish()
        self.assertEqual(self.marked(), [])
        self.editor.setPlainText('typpo ' * 1000)
        self.spelling.refresh()
        self.spelling.set_enabled(False)
        self.assertFalse(self.spelling.batch_timer.isActive())
        self.assertFalse(self.spelling.timer.isActive())
        self.assertEqual(self.marked(), [])
        self.spelling.set_enabled(True)
        self.finish()
        self.assertEqual(self.marked(), ['typpo'] * 1000)

    def test_cross_line_inline_code_exclusions_follow_delimiter_deletion(self):
        self.editor.setPlainText('speling `typpo\nhelo\nwrng` speling\nhello')
        self.finish()
        self.assertEqual(self.marked(), ['speling', 'speling'])
        cursor = QTextCursor(self.editor.document().findBlockByNumber(1))
        last = self.editor.document().findBlockByNumber(2)
        cursor.setPosition(last.position() + 5, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        self.finish()
        expected = [word for _, _, word in prose_words(self.editor.toPlainText())
                    if not self.spelling.known(self.spelling.normalize(word))]
        self.assertEqual(self.marked(), expected)
        self.editor.undo()
        self.finish()
        self.assertEqual(self.marked(), ['speling', 'speling'])

    def test_unicode_offsets_context_menu_and_cache_bound(self):
        self.editor.setPlainText('😀 hello speling\n' + 'hello\n' * 500 + 'helo')
        self.spelling.refresh()
        self.editor.resize(600, 400)
        self.editor.show()
        cursor = QTextCursor(self.editor.document().lastBlock())
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        self.editor.setTextCursor(cursor)
        self.editor.ensureCursorVisible()
        menu = self.spelling.context_menu(self.editor.cursorRect(cursor).center())
        try:
            self.assertTrue(any(action.text() == 'hello' for action in menu.actions()))
        finally:
            menu.deleteLater()
        self.finish()
        self.assertEqual(self.marked(), ['speling', 'helo'])
        self.spelling.CACHE_SIZE = 2
        self.spelling._known_cache.clear()
        for word in ('hello', 'world', 'speling'):
            self.spelling.known(word)
        self.assertEqual(list(self.spelling._known_cache), ['world', 'speling'])
