"""Rules and GFM tables stay editable while their presentation follows the source."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCharFormat, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from main import MarkdownHighlighter, NoteEditor, table_alignment, table_cells
from themes import THEMES


class TablesAndRulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.editor = NoteEditor()
        self.highlighter = MarkdownHighlighter(
            self.editor.document(), THEMES['catppuccin-mocha'], self.editor)
        self.editor.resize(800, 500)
        self.editor.show()

    def tearDown(self):
        self.editor.close()
        self.editor.deleteLater()
        self.app.processEvents()

    def test_table_cells_alignment_and_ragged_rows(self):
        self.assertEqual(table_alignment('|:---|:---:|---:|'),
                         ['left', 'center', 'right'])
        self.assertIsNone(table_alignment('|---|oops|'))
        cells, pipes = table_cells(r'| Text with a \| pipe | `a|b` | |')
        self.assertEqual(len(cells), 3)
        self.assertEqual(len(pipes), 4)
        self.assertEqual(table_cells('| Item 8 | | Unknown | |')[0],
                         [(1, 9), (10, 11), (12, 21), (22, 23)])

    def test_short_delimiters_accept_alignment_but_require_a_hyphen(self):
        self.assertEqual(table_alignment('| - | :-: | --: |'),
                         ['left', 'center', 'right'])
        for delimiter in ('| : | --- |', '| :: | --- |', '| | --- |',
                          '| - - | --- |', '| --x | --- |'):
            with self.subTest(delimiter=delimiter):
                self.assertIsNone(table_alignment(delimiter))

    def test_feature_table_with_two_hyphen_delimiter_renders_and_keeps_source(self):
        source = ('| Feature | Status | Description |\n'
                  '| :--- | :---: | --: |\n'
                  '| **Headings** | Passed | Supports `#` through `######` |\n'
                  '| **Bold & Italic** | Passed | Supports `**bold**` and `*italic*` |\n'
                  '| `Inline Code` | Pending | Renders monospaced code blocks |\n'
                  '| [Links](https://example.com) | Failed | Hyperlink parsing needs work |')
        self.editor.setPlainText(source)
        self.app.processEvents()
        document = self.editor.document()
        document.setModified(False)
        undo_steps = document.availableUndoSteps()
        self.assertEqual([document.findBlockByNumber(i).userState() for i in range(6)],
                         [2, 3, 4, 4, 4, 4])
        self.assertEqual(len(self.editor.table_regions), 1)
        _, alignment, rows = self.editor.table_regions[0]
        self.assertEqual(alignment, ['left', 'center', 'right'])
        self.assertEqual(len(rows), 5)
        self.assertEqual([docs[0].toPlainText() for _, docs in rows],
                         ['Feature', 'Headings', 'Bold & Italic', 'Inline Code', 'Links'])
        # Exercise the painter as well as recognition and cell parsing.
        self.assertFalse(self.editor.viewport().grab().isNull())
        self.assertEqual(self.editor.toPlainText(), source)
        self.assertFalse(document.isModified())
        self.assertEqual(document.availableUndoSteps(), undo_steps)

    def test_table_recognition_updates_and_preserves_source(self):
        source = ('| Name | Description | Status | Price |\n'
                  '|:-----|:-----------|:------:|------:|\n'
                  '| Item 1 | **Bold text** | Active | $10.00 |\n'
                  '| Item 8 | | Unknown | |\n'
                  'After')
        self.editor.setPlainText(source)
        self.app.processEvents()
        document = self.editor.document()
        self.assertEqual([document.findBlockByNumber(i).userState() for i in range(5)],
                         [2, 3, 4, 4, 0])
        self.assertEqual(len(self.editor._table_selections), 4)
        self.assertEqual(len(self.editor.table_regions), 1)
        self.assertEqual(self.editor.table_regions[0][1],
                         ['left', 'left', 'center', 'right'])
        document.setModified(False)
        undo_steps = document.availableUndoSteps()
        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        self.assertEqual(self.editor.toPlainText(), source)
        self.assertFalse(document.isModified())
        self.assertEqual(document.availableUndoSteps(), undo_steps)

        delimiter = document.findBlockByNumber(1)
        cursor = QTextCursor(delimiter)
        cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
        cursor.insertText('not a delimiter\n')
        self.app.processEvents()
        self.assertEqual([document.findBlockByNumber(i).userState() for i in range(4)],
                         [0, 0, 0, 0])

    def test_click_reveals_source_and_leaving_restores_table(self):
        self.editor.setPlainText('| Name | Price |\n|:---|---:|\n| One | $1 |\nAfter')
        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        self.app.processEvents()
        row = self.editor.document().findBlockByNumber(2)
        self.assertIsNone(self.editor._table_edit_position)
        invisible = row.layout().formats()
        self.assertEqual(QTextCharFormat(invisible[-1].format)
                         .foreground().color().alpha(), 0)
        point = self.editor.cursorRect(QTextCursor(row)).center()
        QTest.mouseClick(self.editor.viewport(), Qt.MouseButton.LeftButton, pos=point)
        self.assertEqual(self.editor._table_edit_position, row.position())
        visible = row.layout().formats()
        self.assertEqual(QTextCharFormat(visible[0].format)
                         .foreground().color().alpha(), 255)
        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        self.assertIsNone(self.editor._table_edit_position)
        self.assertEqual(self.editor.toPlainText(),
                         '| Name | Price |\n|:---|---:|\n| One | $1 |\nAfter')

    def test_rule_is_drawn_only_when_inactive_and_disabled_mode_is_plain(self):
        source = 'Before\n---\nAfter\n```\n---\n```'
        self.editor.setPlainText(source)
        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        self.app.processEvents()
        document = self.editor.document()
        rule = document.findBlockByNumber(1)
        code = document.findBlockByNumber(4)
        rule_formats = rule.layout().formats()
        code_formats = code.layout().formats()
        self.assertEqual(QTextCharFormat(rule_formats[0].format)
                         .foreground().color().alpha(), 0)
        self.assertEqual(QTextCharFormat(code_formats[0].format)
                         .foreground().color().alpha(), 255)
        self.editor.setTextCursor(QTextCursor(rule))
        rule_formats = rule.layout().formats()
        self.assertEqual(QTextCharFormat(rule_formats[0].format)
                         .foreground().color().alpha(), 255)
        self.highlighter.enabled = False
        self.highlighter.rehighlight()
        self.editor.update_code_panels()
        self.assertEqual(self.editor._table_selections, [])
        self.assertEqual(rule.layout().formats(), [])
        self.assertEqual(self.editor.toPlainText(), source)

    def test_tab_moves_between_cells_and_enter_adds_an_editable_row(self):
        self.editor.setPlainText('| Name | Price |\n|:---|---:|\n| One | $1 |')
        self.app.processEvents()
        first = self.editor.document().firstBlock()
        self.editor.set_table_cell_cursor(first, table_cells(first.text())[0][0])
        QTest.keyClick(self.editor, Qt.Key.Key_Tab)
        self.assertEqual(self.editor.textCursor().blockNumber(), 0)
        self.assertEqual(self.editor.textCursor().positionInBlock(), 9)
        QTest.keyClick(self.editor, Qt.Key.Key_Tab)
        self.assertEqual(self.editor.textCursor().blockNumber(), 2)
        self.assertEqual(self.editor.textCursor().positionInBlock(), 2)
        QTest.keyClick(self.editor, Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(self.editor.textCursor().blockNumber(), 0)
        self.editor.moveCursor(QTextCursor.MoveOperation.End)
        QTest.keyClick(self.editor, Qt.Key.Key_Return)
        self.app.processEvents()
        self.assertEqual(self.editor.toPlainText(),
                         '| Name | Price |\n|:---|---:|\n| One | $1 |\n|  |  |')
        self.assertEqual(self.editor.textCursor().blockNumber(), 3)
        self.assertEqual(self.editor.document().findBlockByNumber(3).userState(), 4)


if __name__ == '__main__':
    unittest.main()
