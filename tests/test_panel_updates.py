"""Panel caches follow edits without rebuilding unrelated presentation objects."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import random
import unittest
from unittest.mock import patch

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication

from main import MarkdownHighlighter, NoteEditor
from themes import THEMES


class PanelUpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_editor(self, source):
        editor = NoteEditor()
        editor.highlighter = MarkdownHighlighter(
            editor.document(), THEMES['catppuccin-mocha'], editor)
        editor.resize(600, 400)
        editor.setPlainText(source)
        editor.show()
        self.settle()
        return editor

    def setUp(self):
        self.editor = self.make_editor(
            'Body\n' * 1000 + '```\ncode one\n```\nBetween\n'
            '| Name | Price |\n| --- | --- |\n| One | $1 |\n| Two | $2 |\n'
            'After\n```\ncode two\n```\nEnd')

    def tearDown(self):
        self.editor.close()
        self.editor.deleteLater()
        self.app.processEvents()

    def settle(self):
        for _ in range(6):
            self.app.processEvents()

    def block_with_text(self, text):
        cursor = self.editor.document().find(text)
        self.assertFalse(cursor.isNull())
        return cursor.block()

    def snapshot(self, editor):
        return (editor.code_panels,
                [(position, alignment, [(row, [doc.toPlainText() for doc in docs])
                                        for row, docs in rows])
                 for position, alignment, rows in editor.table_regions],
                [s.cursor.position() for s in editor._code_selections],
                [s.cursor.position() for s in editor._table_selections])

    def test_prose_edits_reuse_code_selections_and_table_cells(self):
        e = self.editor
        code = list(e._code_selections)
        cells = [docs for _, docs in e.table_regions[0][2]]
        with patch.object(e, 'record_panel_block', wraps=e.record_panel_block) as records:
            with patch.object(e, 'code_block_selections', wraps=e.code_block_selections) as selections:
                with patch.object(e, 'table_cell_documents', wraps=e.table_cell_documents) as documents:
                    for character in 'typing words':
                        e.insertPlainText(character)
                        self.app.processEvents()
                    # Also move every region through a UTF-16/newline insertion.
                    e.insertPlainText('😀\n')
                    self.settle()
                    selections.assert_not_called()
                    documents.assert_not_called()
                    self.assertLess(records.call_count, 60)
        self.assertTrue(all(a is b for a, b in zip(code, e._code_selections)))
        self.assertTrue(all(a is b for a, (_, b) in zip(cells, e.table_regions[0][2])))
        self.assertEqual(e.document().findBlock(e.code_panels[0][0]).text(), '```')
        self.assertEqual(e.document().findBlock(e.table_regions[0][0]).text(), '| --- | --- |')

    def test_editing_table_row_only_rebuilds_its_cells(self):
        e = self.editor
        before = [docs for _, docs in e.table_regions[0][2]]
        cursor = QTextCursor(self.block_with_text('| One | $1 |'))
        cursor.setPosition(cursor.position() + 3)
        with patch.object(e, 'table_cell_documents', wraps=e.table_cell_documents) as documents:
            with patch.object(e, 'code_block_selections', wraps=e.code_block_selections) as selections:
                cursor.insertText('x')
                self.settle()
                self.assertEqual(documents.call_count, 1)
                selections.assert_not_called()
        after = [docs for _, docs in e.table_regions[0][2]]
        self.assertIs(before[0], after[0])
        self.assertIsNot(before[1], after[1])
        self.assertIs(before[2], after[2])

    def test_code_wrap_edit_only_rebuilds_changed_row(self):
        e = self.editor
        other = self.block_with_text('code two').userData().panel.code_selections
        cursor = QTextCursor(self.block_with_text('code one'))
        with patch.object(e, 'code_block_selections', wraps=e.code_block_selections) as selections:
            with patch.object(e, 'table_cell_documents', wraps=e.table_cell_documents) as documents:
                cursor.insertText('A long code line with several words. ' * 20)
                self.settle()
                self.assertEqual(selections.call_count, 1)
                documents.assert_not_called()
        self.assertIs(self.block_with_text('code two').userData().panel.code_selections, other)
        block = cursor.block()
        self.assertGreater(block.layout().lineCount(), 1)
        self.assertEqual(len(block.userData().panel.code_selections), block.layout().lineCount())

    def test_structural_edits_match_fresh_document(self):
        e = self.editor
        e.setPlainText('Before\n```\ncode\n```\n| A | B |\n| --- | --- |\n| x | y |\nEnd')
        self.settle()
        rng = random.Random(19)
        for _ in range(40):
            source = e.toPlainText()
            start = rng.randrange(len(source) + 1)
            end = rng.randrange(start, len(source) + 1)
            cursor = QTextCursor(e.document())
            cursor.setPosition(len(source[:start].encode('utf-16-le')) // 2)
            cursor.setPosition(len(source[:end].encode('utf-16-le')) // 2,
                               QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(rng.choice(('```\n', '\n', '😀', '', '| a | b |\n| - | - |\n')))
            self.settle()
            fresh = self.make_editor(e.toPlainText())
            try:
                self.assertEqual(self.snapshot(e), self.snapshot(fresh))
            finally:
                fresh.close()
                fresh.deleteLater()
                self.app.processEvents()
