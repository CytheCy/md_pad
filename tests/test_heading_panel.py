"""Heading navigation follows edits without changing the note."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import random
import re
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

    def test_initial_file_uses_narrow_width_after_window_shows(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        settings = QSettings('Pad', 'Pad')
        settings.setValue('heading_panel_state', 'narrow')
        settings.setValue('heading_panel_width', 400)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'note.md'
            path.write_text('# Longer heading\n## Another heading\n')
            self.window = MainWindow(path)
            self.editor = self.window.editor
            self.window.show()
            self.app.processEvents()
            self.assertEqual(self.window.heading_list.item(0).text(), 'Lon')
            self.assertEqual(self.window.content_splitter.sizes()[1],
                             self.window.heading_panel_compact_width())
            self.assertEqual(settings.value('heading_panel_width', type=int), 400)

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

    def test_body_edits_keep_rows_selection_scroll_and_panel_width(self):
        w = self.window
        self.editor.setPlainText('Intro\n' + '# Same\nBody\n' * 100)
        for _ in range(6):
            self.app.processEvents()
        items = [w.heading_list.item(i) for i in range(100)]
        w.heading_list.setCurrentItem(items[60])
        bar = w.heading_list.verticalScrollBar()
        bar.setValue(25)
        scroll = bar.value()
        width = w.content_splitter.sizes()[1]
        self.editor.moveCursor(QTextCursor.MoveOperation.Start)
        with patch.object(w.heading_list, 'clear') as clear:
            with patch.object(w, 'update_heading_panel_display') as display:
                with patch.object(w, 'resize_heading_panel') as resize:
                    self.editor.insertPlainText('😀 inserted\n')
                    for _ in range(6):
                        self.app.processEvents()
                    clear.assert_not_called()
                    display.assert_not_called()
                    resize.assert_not_called()
        self.assertTrue(all(w.heading_list.item(i) is item for i, item in enumerate(items)))
        self.assertIs(w.heading_list.currentItem(), items[60])
        self.assertEqual(bar.value(), scroll)
        self.assertEqual(w.content_splitter.sizes()[1], width)
        # The original row still navigates correctly after a Unicode insertion.
        document = self.editor.document()
        expected = document.findBlockByNumber(122).position()
        w.go_to_heading(items[60])
        self.assertEqual(self.editor.textCursor().position(), expected)

    def test_renaming_and_changing_level_reuses_heading_row(self):
        w = self.window
        self.editor.setPlainText('# First\nBody\n## Second')
        self.app.processEvents()
        w.set_heading_panel_state('full')
        first, second = w.heading_list.item(0), w.heading_list.item(1)
        cursor = QTextCursor(self.editor.document().firstBlock())
        cursor.select(QTextCursor.SelectionType.LineUnderCursor)
        cursor.insertText('### Renamed')
        self.app.processEvents()
        self.assertIs(w.heading_list.item(0), first)
        self.assertIs(w.heading_list.item(1), second)
        self.assertEqual(first.text(), '    Renamed')
        self.assertEqual(first.toolTip(), 'Renamed')
        self.editor.undo()
        self.assertIs(w.heading_list.item(0), first)
        self.assertEqual(first.text(), 'First')

    def test_inserting_and_removing_heading_preserves_other_rows(self):
        w = self.window
        self.editor.setPlainText('# First\nBody\n## Second\nMore\n### Third')
        self.app.processEvents()
        items = [w.heading_list.item(i) for i in range(3)]
        cursor = QTextCursor(self.editor.document().findBlockByNumber(1))
        cursor.insertText('# Added\n')
        self.app.processEvents()
        self.assertEqual(w.heading_list.count(), 4)
        self.assertEqual([w.heading_list.item(i) for i in (0, 2, 3)], items)
        self.editor.undo()
        self.app.processEvents()
        self.assertEqual(w.heading_list.count(), 3)
        self.assertEqual([w.heading_list.item(i) for i in range(3)], items)
        self.editor.redo()
        self.app.processEvents()
        self.assertEqual([w.heading_list.item(i) for i in (0, 2, 3)], items)

    def assert_heading_index_matches_source(self):
        expected = []
        in_code = False
        offset = 0
        for line in self.editor.toPlainText().split('\n'):
            if re.match(r'^\s*(`{3,}|~{3,})', line):
                in_code = not in_code
            elif not in_code:
                match = re.match(r'^(#{1,6})\s+(.*)$', line)
                if match:
                    title = re.sub(r'\s+#+\s*$', '', match[2]).strip()
                    expected.append((offset, len(match[1]), title or 'Untitled heading'))
            offset += len(line.encode('utf-16-le')) // 2 + 1
        self.assertEqual(self.window.headings, expected)
        self.assertEqual(self.window.heading_list.count(), len(expected))

    def test_fence_edits_reclassify_later_headings_and_undo_restores_them(self):
        self.editor.setPlainText('# First\n```\n# Hidden\n```\n# Visible\nBody\n## Last')
        self.app.processEvents()
        self.assert_heading_index_matches_source()
        cursor = QTextCursor(self.editor.document().findBlockByNumber(1))
        cursor.deleteChar()
        self.assert_heading_index_matches_source()
        self.assertEqual([title for _, _, title in self.window.headings], ['First', 'Hidden'])
        self.editor.undo()
        self.assert_heading_index_matches_source()
        self.editor.redo()
        self.assert_heading_index_matches_source()

    def test_incremental_index_handles_multiline_paste_delete_and_joins(self):
        self.editor.setPlainText('# First\nBody 😀\n```\n# Hidden\n```\n## Last\nTail')
        self.app.processEvents()
        rng = random.Random(37)
        for _ in range(60):
            source = self.editor.toPlainText()
            start = rng.randrange(len(source) + 1)
            end = rng.randrange(start, len(source) + 1)
            replacement = rng.choice(('# Added\n', '\n', '```\n', '~~~\n', '', '😀', ' body '))
            cursor = QTextCursor(self.editor.document())
            cursor.setPosition(len(source[:start].encode('utf-16-le')) // 2)
            cursor.setPosition(len(source[:end].encode('utf-16-le')) // 2,
                               QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(replacement)
            self.assert_heading_index_matches_source()
            self.app.processEvents()
        self.editor.undo()
        self.assert_heading_index_matches_source()
