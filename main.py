#!/usr/bin/env python3
"""MDPad: a small native editor for Markdown and plain text."""

from __future__ import annotations

import argparse
import codecs
from functools import lru_cache
import re
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QRectF, QSaveFile, QSettings, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QClipboard,
    QDesktopServices,
    QFont,
    QIcon,
    QKeySequence,
    QPalette,
    QPainter,
    QPainterPath,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFormat,
    QSyntaxHighlighter,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QRadioButton,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenuBar,
    QMessageBox,
    QSpinBox,
    QSplitter,
    QTextEdit,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtSvg import QSvgRenderer


from themes import (THEMES, apply_application_theme, resolve_theme, saved_theme_id)
from spelling import Spelling
from updater import UpdatesDialog


APP_NAME = "MDPad"
FILE_FILTER = "Notes (*.md *.markdown *.txt);;Markdown (*.md *.markdown);;Text (*.txt);;All files (*)"
MAX_RECENT_FILES = 10
DEFAULT_FONT_SIZE = 12
MIN_FONT_SIZE = 6
MAX_FONT_SIZE = 72


@lru_cache(maxsize=32)
def boxicon(name: str, color: str) -> QSvgRenderer:
    """Load a bundled Boxicons SVG with the current theme color."""
    source = (Path(__file__).resolve().parent / "boxicons" / f"bx-{name}.svg").read_text()
    source = source.replace("<svg ", f'<svg fill="{color}" ', 1)
    return QSvgRenderer(source.encode())


def fmt(color: str | None = None, *, bold: bool = False, italic: bool = False,
        size: float | None = None, family: str | None = None) -> QTextCharFormat:
    result = QTextCharFormat()
    if color:
        result.setForeground(QColor(color))
    if bold:
        result.setFontWeight(QFont.Weight.Bold)
    if italic:
        result.setFontItalic(True)
    if size:
        result.setFontPointSize(size)
    if family:
        result.setFontFamilies([family])
    return result


def web_link_at(text: str, offset: int, markdown: bool = True) -> str | None:
    """Find a web link at a character offset in one source line."""
    if markdown:
        for code in re.finditer(r"(?<!`)(`+)([^`\n]+)\1(?!`)", text):
            if code.start() <= offset < code.end():
                return None
        for match in re.finditer(r"(?<!!)\[([^\]\n]+)\]\(", text):
            if not match.start(1) <= offset < match.end(1):
                continue
            start = match.end()
            depth = 1
            for end in range(start, len(text)):
                if text[end] == '(':
                    depth += 1
                elif text[end] == ')':
                    depth -= 1
                    if depth == 0:
                        url = text[start:end]
                        if re.fullmatch(r'(?:https?://|www\.)[^\s]+', url):
                            return url if url.startswith('http') else 'https://' + url
                        return None
    for match in re.finditer(r"(?:https?://|www\.)[^\s<>\[\]`]+", text):
        url = match.group().rstrip('.,;:!?]}')
        while url.endswith(')') and url.count(')') > url.count('('):
            url = url[:-1]
        end = match.start() + len(url)
        if match.start() <= offset < end:
            return url if url.startswith('http') else 'https://' + url
    return None


def table_cells(line: str):
    """Return cell and pipe spans, ignoring escaped and code-span pipes."""
    pipes = []
    code_run = 0
    index = 0
    while index < len(line):
        char = line[index]
        if char == '\\':
            start = index
            while index < len(line) and line[index] == '\\':
                index += 1
            if (index - start) % 2 and index < len(line):
                index += 1
            continue
        if char == '`':
            end = index
            while end < len(line) and line[end] == '`':
                end += 1
            run = end - index
            if code_run == run:
                code_run = 0
            elif not code_run and line.find('`' * run, end) != -1:
                code_run = run
            index = end
            continue
        if char == '|' and not code_run:
            pipes.append(index)
        index += 1
    if not pipes:
        return None
    starts = [0] + [pipe + 1 for pipe in pipes]
    ends = pipes + [len(line)]
    cells = list(zip(starts, ends))
    if not line[:pipes[0]].strip():
        cells.pop(0)
    if not line[pipes[-1] + 1:].strip():
        cells.pop()
    return (cells, pipes) if cells else None


def table_alignment(line: str):
    parsed = table_cells(line)
    if parsed is None:
        return None
    cells, _ = parsed
    if not cells:
        return None
    alignment = []
    for start, end in cells:
        marker = line[start:end].strip()
        if not re.fullmatch(r':?-{3,}:?', marker):
            return None
        alignment.append('center' if marker.startswith(':') and marker.endswith(':')
                         else 'right' if marker.endswith(':') else 'left')
    return alignment


class MarkdownHighlighter(QSyntaxHighlighter):
    """Style source text in place, keeping every Markdown character editable."""

    def __init__(self, document, theme, editor=None):
        super().__init__(document)
        self.enabled = True
        self.editor = editor
        self.active_block = editor.textCursor().block() if editor else None
        self.active_code_panel = None
        if editor:
            editor.highlighter = self
            editor.cursorPositionChanged.connect(self.update_active_block)
            editor.textChanged.connect(editor.schedule_code_panel_update)
        self.update_colors(theme)

    def update_active_block(self):
        block = self.editor.textCursor().block()
        if block == self.active_block:
            return
        document = self.document()
        was_modified = document.isModified()
        previous = self.active_block
        self.active_block = block
        if (self.editor._table_edit_position is not None
                and block.position() != self.editor._table_edit_position):
            self.editor._table_edit_position = None
        if previous is not None and previous.isValid():
            self.rehighlightBlock(previous)
        self.rehighlightBlock(block)
        self.sync_active_code_panel()
        # Rehighlighting after block-format changes can mark Qt's document dirty.
        # Cursor movement only changes the display, never the note itself.
        if document.isModified() != was_modified:
            document.setModified(was_modified)
        self.editor.viewport().update()

    def sync_active_code_panel(self):
        if not self.editor:
            return
        position = self.editor.textCursor().block().position()
        active = next(((start, end) for start, end in self.editor.code_panels
                       if start <= position <= end), None)
        if active == self.active_code_panel:
            return
        previous = self.active_code_panel
        self.active_code_panel = active
        for panel in (previous, active):
            if panel:
                for fence_position in set(panel):
                    self.rehighlightBlock(self.document().findBlock(fence_position))

    def code_fence_is_active(self):
        panel = self.active_code_panel
        return panel is not None and self.currentBlock().position() in panel

    def update_colors(self, theme):
        self.theme = theme
        self.muted = theme['md_marker']
        self.accent = theme['md_link']
        self.code = theme['md_code']
        self.quote = theme['md_quote']
        self.rehighlight()
        if self.editor:
            self.editor.update_code_panels()

    def code_format(self):
        style = fmt(self.code, family="monospace")
        style.setBackground(QColor(self.theme['md_code_background']))
        return style

    def code_block_format(self):
        return fmt(self.theme['text'], family="monospace")

    def collapsed_marker_format(self):
        marker = QTextCharFormat()
        marker.setForeground(QColor(Qt.GlobalColor.transparent))
        marker.setFontPointSize(0.01)
        marker.setFontLetterSpacingType(QFont.SpacingType.PercentageSpacing)
        marker.setFontLetterSpacing(1)
        return marker

    def source_format(self, start, length, style):
        # Python regex offsets count code points; Qt counts UTF-16 units.
        offset = len(self.block_text[:start].encode('utf-16-le')) // 2
        count = len(self.block_text[start:start + length].encode('utf-16-le')) // 2
        self.setFormat(offset, count, style)

    def highlightBlock(self, text: str):  # noqa: N802 (Qt API)
        self.block_text = text
        self.setCurrentBlockState(0)
        if not self.enabled:
            return
        if self.previousBlockState() == 1:
            self.setCurrentBlockState(1)
            self.source_format(0, len(text), self.code_block_format())
            closing_fence = re.match(r"^\s*(`{3,}|~{3,})", text)
            if closing_fence:
                self.setCurrentBlockState(0)
                self.source_format(0, len(text), fmt(self.muted, family="monospace"))
                if (closing_fence.group(1).startswith('`')
                        and not self.code_fence_is_active()):
                    self.source_format(0, len(text), fmt(Qt.GlobalColor.transparent, family="monospace"))
            return

        fence = re.match(r"^\s*(`{3,}|~{3,})", text)
        if fence:
            self.setCurrentBlockState(1)
            self.source_format(0, len(text), fmt(self.muted, family="monospace"))
            if (fence.group(1).startswith('`')
                    and not self.code_fence_is_active()):
                self.source_format(0, len(text), fmt(Qt.GlobalColor.transparent, family="monospace"))
            return

        table = None
        parsed = table_cells(text)
        previous = self.previousBlockState()
        if parsed is not None:
            cells, pipes = parsed
            next_block = self.currentBlock().next()
            next_alignment = (table_alignment(next_block.text())
                              if next_block.isValid() else None)
            if next_alignment is not None and len(cells) == len(next_alignment):
                table = 'header'
                self.setCurrentBlockState(2)
            elif (previous == 2 and table_alignment(text) is not None
                  and len(cells) == len(table_cells(self.currentBlock().previous().text())[0])):
                table = 'delimiter'
                self.setCurrentBlockState(3)
            elif previous in (3, 4):
                table = 'body'
                self.setCurrentBlockState(4)

        heading = re.match(r"^(#{1,6})(\s+)(.*)$", text) if table is None else None
        if heading:
            level = len(heading.group(1))
            size = ([25, 21, 18, 16, 14, 13][level - 1]
                    * self.document().defaultFont().pointSizeF() / DEFAULT_FONT_SIZE)
            self.source_format(0, len(text), fmt(self.theme['md_heading'] if level <= 2 else self.theme['md_heading_secondary'], bold=True, size=size))
            marker = fmt(self.muted, size=size)
            if self.currentBlock() != self.active_block:
                # Collapse the prefix visually without changing the Markdown source.
                marker.setForeground(QColor(Qt.GlobalColor.transparent))
                marker.setFontPointSize(0.01)
                marker.setFontLetterSpacingType(QFont.SpacingType.PercentageSpacing)
                marker.setFontLetterSpacing(1)
            self.source_format(0, heading.end(2), marker)
        elif table:
            if table == 'header':
                self.source_format(0, len(text), fmt(self.theme['md_heading_secondary'], bold=True))
            elif table == 'delimiter':
                self.source_format(0, len(text), fmt(self.muted))
            for pipe in pipes:
                self.source_format(pipe, 1, fmt(self.muted))
        elif re.match(r"^ {0,3}(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})$", text):
            marker = (self.collapsed_marker_format() if self.currentBlock() != self.active_block
                      else fmt(self.theme['md_rule']))
            self.source_format(0, len(text), marker)
        else:
            lead = re.match(r"^(\s*(?:>\s*|[-*+]\s+|\d+[.)]\s+|\[[ xX]\]\s+)+)", text)
            if lead:
                self.source_format(0, lead.end(), fmt(self.theme['md_list']))
                list_marker = re.match(r"^(?:[-*+] |\d+[.)] )", text)
                if list_marker and self.currentBlock() != self.active_block:
                    marker = QTextCharFormat()
                    marker.setForeground(QColor(Qt.GlobalColor.transparent))
                    marker.setFontLetterSpacingType(QFont.SpacingType.AbsoluteSpacing)
                    marker.setFontLetterSpacing(5)
                    self.source_format(0, list_marker.end(), marker)
                checkbox = re.search(r'\[[ xX]\]', lead.group(1))
                if checkbox:
                    self.source_format(checkbox.start(), 3, fmt(self.theme['md_checkbox']))
                if ">" in lead.group(1):
                    self.source_format(lead.end(), len(text) - lead.end(), fmt(self.quote))

        # Format emphasis content while collapsing its source marks off the active line.
        code_matches = list(re.finditer(r"(?<!`)(`+)([^`\n]+)\1(?!`)", text))
        code_spans = [(m.start(), m.end()) for m in code_matches]
        for pattern, styled in (
            (r"(?<!\*)\*\*([^*\n]+)\*\*(?!\*)|__([^_\n]+)__", fmt(self.theme['md_bold'], bold=True)),
            (r"(?<!\*)\*([^*\n]+)\*(?!\*)|(?<!_)_([^_\n]+)_(?!_)", fmt(self.theme['md_italic'], italic=True)),
        ):
            for match in re.finditer(pattern, text):
                if any(match.start() < end and start < match.end()
                       for start, end in code_spans):
                    continue
                content = 1 if match.start(1) != -1 else 2
                self.source_format(match.start(content),
                                   match.end(content) - match.start(content), styled)
                marker = fmt(self.muted)
                if self.currentBlock() != self.active_block:
                    marker = self.collapsed_marker_format()
                self.source_format(match.start(), match.start(content) - match.start(), marker)
                self.source_format(match.end(content), match.end() - match.end(content), marker)

        for match in code_matches:
            self.source_format(match.start(), match.end() - match.start(), self.code_format())
            if self.currentBlock() != self.active_block:
                marker = self.collapsed_marker_format()
                self.source_format(match.start(), match.start(2) - match.start(), marker)
                self.source_format(match.end(2), match.end() - match.end(2), marker)
        for match in re.finditer(r"!?\[[^\]\n]+\]\([^\)\n]+\)", text):
            self.source_format(match.start(), match.end() - match.start(), fmt(self.accent))
        if table and (self.editor is None or
                      self.editor._table_edit_position != self.currentBlock().position()):
            self.source_format(0, len(text), fmt(Qt.GlobalColor.transparent))


class NoteEditor(QTextEdit):
    files_dropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.max_page_width = 0
        self._spelling_selections = []
        self._code_selections = []
        self._table_selections = []
        self._find_selections = []
        self.code_panels = []
        self.table_regions = []
        self._table_edit_position = None
        self._copy_pressed_panel = None
        self._hovered_code_panel = None
        self._hovered_link = False
        self._pressed_link = None
        self._code_update_timer = QTimer(self)
        self._code_update_timer.setSingleShot(True)
        self._code_update_timer.timeout.connect(self.update_code_panels)
        self.setAcceptDrops(True)
        self.setAcceptRichText(False)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setPlaceholderText("Start writing…")
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.viewport().setMouseTracking(True)
        self.viewport().installEventFilter(self)
        # Leave room for code panels while keeping prose in its original position.
        self.document().setDocumentMargin(24)
        self.setViewportMargins(26, 10, 26, 10)

    def setExtraSelections(self, selections):  # noqa: N802 (Qt API)
        self._spelling_selections = list(selections)
        self.refresh_extra_selections()

    def setPlainText(self, text):  # noqa: N802 (Qt API)
        self._table_edit_position = None
        super().setPlainText(text)

    def clear(self):
        self._table_edit_position = None
        super().clear()

    def refresh_extra_selections(self):
        super().setExtraSelections(
            self._code_selections + self._table_selections
            + self._find_selections + self._spelling_selections)

    def extraSelections(self):  # noqa: N802 (Qt API)
        return self._spelling_selections

    def schedule_code_panel_update(self):
        self._code_update_timer.start(0)

    def update_code_panels(self):
        highlighter = getattr(self, 'highlighter', None)
        if highlighter is not None and highlighter.enabled:
            # A table header depends on the following delimiter line.
            was_modified = self.document().isModified()
            highlighter.rehighlight()
            self.document().setModified(was_modified)
        self.code_panels = []
        self._code_selections = []
        self._table_selections = []
        self._hovered_code_panel = None
        self.viewport().unsetCursor()
        if highlighter is not None and highlighter.enabled:
            opening = None
            block = self.document().firstBlock()
            while block.isValid():
                if block.userState() in (2, 3, 4):
                    selection = QTextEdit.ExtraSelection()
                    selection.cursor = QTextCursor(block)
                    shade = QColor(highlighter.theme['elevated'])
                    if block.userState() == 4 and block.blockNumber() % 2:
                        shade.setAlpha(110)
                    selection.format.setBackground(shade)
                    selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
                    self._table_selections.append(selection)
                if opening is None and block.userState() == 1 and re.match(
                        r"^\s*(?:`{3,}|~{3,})", block.text()):
                    opening = block
                if opening is not None:
                    self.document().documentLayout().blockBoundingRect(block)
                    layout = block.layout()
                    for index in range(max(1, layout.lineCount())):
                        line = layout.lineAt(index) if layout.lineCount() else None
                        offset = line.textStart() + (1 if line.textLength() > 1 else 0) if line else 0
                        selection = QTextEdit.ExtraSelection()
                        selection.cursor = QTextCursor(block)
                        selection.cursor.setPosition(block.position() + offset)
                        selection.format.setBackground(QColor(highlighter.theme['md_code_background']))
                        selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
                        self._code_selections.append(selection)
                    if block.userState() == 0 or not block.next().isValid():
                        self.code_panels.append((opening.position(), block.position()))
                        opening = None
                block = block.next()
            self.update_table_regions()
        self.refresh_extra_selections()
        if highlighter is not None:
            was_modified = self.document().isModified()
            highlighter.sync_active_code_panel()
            self.document().setModified(was_modified)
        self.viewport().update()

    def update_table_regions(self):
        self.table_regions = []
        block = self.document().firstBlock()
        while block.isValid():
            if block.userState() != 2:
                block = block.next()
                continue
            delimiter = block.next()
            if not delimiter.isValid() or delimiter.userState() != 3:
                block = block.next()
                continue
            alignment = table_alignment(delimiter.text())
            rows = []
            current = block
            while current.isValid() and current.userState() in (2, 3, 4):
                if current.userState() != 3:
                    docs = []
                    for start, end in table_cells(current.text())[0]:
                        cell = current.text()[start:end].strip()
                        doc = QTextDocument()
                        doc.setDocumentMargin(0)
                        doc.setDefaultFont(self.font())
                        doc.setMarkdown(cell, QTextDocument.MarkdownFeature.MarkdownDialectGitHub)
                        content = QTextCursor(doc)
                        content.select(QTextCursor.SelectionType.Document)
                        style = fmt(self.highlighter.theme['md_heading_secondary']
                                    if current.userState() == 2 else self.highlighter.theme['text'],
                                    bold=current.userState() == 2)
                        content.mergeCharFormat(style)
                        docs.append(doc)
                    rows.append((current.position(), docs))
                current = current.next()
            self.table_regions.append((delimiter.position(), alignment, rows))
            block = current

    def keyPressEvent(self, event):  # noqa: N802 (Qt API)
        if (getattr(self, 'highlighter', None) is not None
                and self.highlighter.enabled and not self.textCursor().hasSelection()
                and self.textCursor().block().userState() in (2, 4)):
            self._table_edit_position = self.textCursor().block().position()
            self.highlighter.rehighlightBlock(self.textCursor().block())
            if event.key() == Qt.Key.Key_Tab and event.modifiers() in (
                    Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ShiftModifier):
                if self.move_table_cell(event.modifiers() == Qt.KeyboardModifier.ShiftModifier):
                    event.accept()
                    return
            if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                    and event.modifiers() == Qt.KeyboardModifier.NoModifier
                    and self.textCursor().block().userState() == 4
                    and self.textCursor().atBlockEnd()):
                self.insert_table_row(self.textCursor().block())
                event.accept()
                return
        if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and event.modifiers() == Qt.KeyboardModifier.NoModifier):
            cursor = self.textCursor()
            if not cursor.hasSelection():
                line = cursor.block().text()
                bullet = re.match(r"^([-*+]) ", line)
                numbered = re.match(r"^(\d+)([.)]) ", line)
                marker = bullet or numbered
                if marker and cursor.positionInBlock() >= marker.end():
                    if line == marker.group(0):
                        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock,
                                            QTextCursor.MoveMode.KeepAnchor)
                        cursor.removeSelectedText()
                    else:
                        if numbered:
                            number = str(int(numbered.group(1)) + 1).zfill(len(numbered.group(1)))
                            next_marker = number + numbered.group(2) + ' '
                        else:
                            next_marker = bullet.group(0)
                        cursor.insertText("\n" + next_marker)
                    self.setTextCursor(cursor)
                    event.accept()
                    return
        super().keyPressEvent(event)

    def set_table_cell_cursor(self, block, cell):
        start, end = cell
        text = block.text()
        start += len(text[start:end]) - len(text[start:end].lstrip())
        offset = len(text[:start].encode('utf-16-le')) // 2
        cursor = QTextCursor(block)
        cursor.setPosition(block.position() + offset)
        self._table_edit_position = block.position()
        self.setTextCursor(cursor)
        self.highlighter.rehighlightBlock(block)

    def insert_table_row(self, after_block):
        parsed = table_cells(after_block.text())
        count = len(parsed[0])
        row = '| ' + ' | '.join([''] * count) + ' |'
        cursor = QTextCursor(after_block)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        cursor.insertText('\n' + row)
        self.set_table_cell_cursor(cursor.block(), table_cells(row)[0][0])

    def move_table_cell(self, backwards):
        block = self.textCursor().block()
        parsed = table_cells(block.text())
        if parsed is None:
            return False
        cells, _ = parsed
        offset = self.textCursor().positionInBlock()
        index = next((i for i, (_, end) in enumerate(cells) if offset <= end),
                     len(cells) - 1)
        target = index + (-1 if backwards else 1)
        if 0 <= target < len(cells):
            self.set_table_cell_cursor(block, cells[target])
            return True
        if backwards:
            other = block.previous()
            if other.userState() == 3:
                other = other.previous()
            if other.userState() not in (2, 4):
                return False
            self.set_table_cell_cursor(other, table_cells(other.text())[0][-1])
        else:
            other = block.next()
            if other.userState() == 3:
                other = other.next()
            if other.userState() == 4:
                self.set_table_cell_cursor(other, table_cells(other.text())[0][0])
            else:
                after = block.next() if block.userState() == 2 else block
                self.insert_table_row(after)
        return True

    def paintEvent(self, event):  # noqa: N802 (Qt API)
        super().paintEvent(event)
        highlighter = getattr(self, 'highlighter', None)
        if highlighter is None or not highlighter.enabled:
            return
        painter = QPainter(self.viewport())
        self.paint_code_panels(painter, event.rect())
        self.paint_tables(painter, event.rect())
        painter.setPen(QColor(highlighter.theme['md_rule']))
        inset = self.document().documentMargin()
        rule_right = self.viewport().width() - inset
        active_block = self.textCursor().block()
        block = self.cursorForPosition(event.rect().topLeft()).block()
        while block.isValid():
            cursor = QTextCursor(block)
            rect = self.cursorRect(cursor)
            if rect.top() > event.rect().bottom():
                break
            if (block != active_block and block.userState() != 1
                    and re.fullmatch(r" {0,3}(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})", block.text())):
                y = rect.center().y()
                painter.drawLine(int(rect.left()), y, int(rule_right), y)
            block = block.next()
        painter.setPen(Qt.PenStyle.NoPen)
        list_color = QColor(highlighter.theme['md_list'])
        painter.setBrush(list_color)
        block = self.cursorForPosition(event.rect().topLeft()).block()
        while block.isValid():
            cursor = QTextCursor(block)
            start = self.cursorRect(cursor)
            if start.top() > event.rect().bottom():
                break
            line = block.text()
            bullet = re.match(r"^[-*+] ", line)
            numbered = re.match(r"^(\d+)[.)] ", line)
            if (block != active_block and block.userState() != 1
                    and (numbered or (bullet and not re.match(
                        r"^\s*(?:[-*_]\s*){3,}$", line)))):
                marker = numbered or bullet
                cursor.setPosition(block.position() + marker.end())
                end = self.cursorRect(cursor)
                marker_area = QRectF(start.left(), start.top(),
                                     end.left() - start.left(), start.height())
                if numbered:
                    painter.setPen(list_color)
                    marker_area.setRight(marker_area.right() - 4)
                    painter.drawText(marker_area, Qt.AlignmentFlag.AlignRight |
                                     Qt.AlignmentFlag.AlignVCenter, numbered.group(1) + '.')
                else:
                    painter.setPen(Qt.PenStyle.NoPen)
                    radius = max(3.0, self.fontMetrics().height() * 0.19)
                    painter.drawEllipse(marker_area.center(), radius, radius)
            block = block.next()
        painter.end()

    def paint_tables(self, painter, dirty):
        theme = self.highlighter.theme
        document = self.document()
        editing = self._table_edit_position
        left_margin = document.documentMargin()
        for delimiter_position, alignment, rows in self.table_regions:
            delimiter = document.findBlock(delimiter_position)
            if editing == delimiter_position or not rows:
                continue
            first = document.findBlock(rows[0][0])
            left = self.cursorRect(QTextCursor(first)).left()
            available = max(1, self.viewport().width() - left - left_margin)
            count = len(alignment)
            natural = [max(64.0, max((docs[i].idealWidth() + 24
                                      for _, docs in rows if i < len(docs)), default=64.0))
                       for i in range(count)]
            total = sum(natural)
            if total <= available:
                widths = [width + (available - total) / count for width in natural]
            else:
                widths = [available * width / total for width in natural]
            boundaries = [left]
            for width in widths:
                boundaries.append(boundaries[-1] + width)
            for row_index, (position, docs) in enumerate(rows):
                block = document.findBlock(position)
                top = self.cursorRect(QTextCursor(block)).top()
                if row_index + 1 < len(rows):
                    bottom = self.cursorRect(QTextCursor(
                        document.findBlock(rows[row_index + 1][0]))).top()
                else:
                    last = QTextCursor(block)
                    last.movePosition(QTextCursor.MoveOperation.EndOfBlock)
                    bottom = self.cursorRect(last).bottom() + 7
                row_rect = QRectF(left, top, available, bottom - top)
                if not row_rect.intersects(QRectF(dirty)):
                    continue
                if position != editing:
                    shade = theme['elevated'] if row_index == 0 or row_index % 2 == 0 else theme['editor']
                    painter.fillRect(row_rect, QColor(shade))
                painter.setPen(QColor(theme['border']))
                painter.drawRect(row_rect)
                for column in range(1, count):
                    painter.drawLine(int(boundaries[column]), int(top),
                                     int(boundaries[column]), int(bottom))
                if position == editing:
                    continue
                for column, doc in enumerate(docs[:count]):
                    width = max(1, widths[column] - 16)
                    doc.setTextWidth(width)
                    content = QTextCursor(doc)
                    content.select(QTextCursor.SelectionType.Document)
                    paragraph = content.blockFormat()
                    paragraph.setAlignment({'left': Qt.AlignmentFlag.AlignLeft,
                                            'center': Qt.AlignmentFlag.AlignHCenter,
                                            'right': Qt.AlignmentFlag.AlignRight}[alignment[column]])
                    content.mergeBlockFormat(paragraph)
                    painter.save()
                    cell = QRectF(boundaries[column] + 8, top, width, bottom - top)
                    painter.setClipRect(cell)
                    scale = min(1.0, max(0.1, (cell.height() - 2) / doc.size().height()))
                    offset = (cell.width() * (1 - scale) *
                              (1 if alignment[column] == 'right' else
                               0.5 if alignment[column] == 'center' else 0))
                    painter.translate(cell.left() + offset,
                                      cell.top() + (cell.height() - doc.size().height() * scale) / 2)
                    painter.scale(scale, scale)
                    doc.drawContents(painter, QRectF(0, 0, width, doc.size().height()))
                    painter.restore()

    def code_panel_rect(self, start_position, end_position):
        document = self.document()
        first = QTextCursor(document.findBlock(start_position))
        last = QTextCursor(document.findBlock(end_position))
        last.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        top = self.cursorRect(first).top()
        bottom = self.cursorRect(last).bottom() + 1
        return QRectF(0, top, self.viewport().width(), bottom - top)

    def code_copy_rect(self, panel):
        return QRectF(panel.right() - 42, panel.top() + 10, 30, 30)

    def code_panel_at(self, position):
        if getattr(self, 'highlighter', None) is None or not self.highlighter.enabled:
            return None
        return next(((start, end) for start, end in self.code_panels
                     if self.code_panel_rect(start, end).contains(position)), None)

    def mouseMoveEvent(self, event):  # noqa: N802 (Qt API)
        super().mouseMoveEvent(event)
        hovered = self.code_panel_at(event.position())
        if hovered != self._hovered_code_panel:
            self._hovered_code_panel = hovered
            self.viewport().update()
        over_copy = (hovered is not None and self.code_copy_rect(
            self.code_panel_rect(*hovered)).contains(event.position()))
        over_link = not over_copy and self.web_link_at_position(event.position()) is not None
        if over_link != self._hovered_link:
            if over_link:
                QApplication.setOverrideCursor(Qt.CursorShape.PointingHandCursor)
            else:
                QApplication.restoreOverrideCursor()
            self._hovered_link = over_link
        if over_copy:
            self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
            self.viewport().setToolTip("Copy code")
        elif over_link:
            self.viewport().setToolTip("Open link")
        else:
            self.viewport().unsetCursor()
            self.viewport().setToolTip("")

    def web_link_at_position(self, position):
        cursor = self.cursorForPosition(position.toPoint())
        block = cursor.block()
        if not block.isValid():
            return None
        highlighter = getattr(self, 'highlighter', None)
        markdown = highlighter is not None and highlighter.enabled
        if markdown and block.userState() == 1:
            return None
        offset = cursor.positionInBlock()
        if offset and self.cursorRect(cursor).left() > position.x():
            offset -= 1
        # QTextCursor offsets use UTF-16 units; Python strings use code points.
        text = block.text()
        offset = len(text.encode('utf-16-le')[:offset * 2].decode('utf-16-le', errors='ignore'))
        return web_link_at(text, offset, markdown)

    def eventFilter(self, watched, event):  # noqa: N802 (Qt API)
        if (watched is self.viewport()
                and event.type() in (QEvent.Type.Leave, QEvent.Type.Hide)):
            if self._hovered_link:
                QApplication.restoreOverrideCursor()
                self._hovered_link = False
            if self._hovered_code_panel is not None:
                self._hovered_code_panel = None
                self.viewport().update()
            self.viewport().unsetCursor()
            self.viewport().setToolTip("")
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event):  # noqa: N802 (Qt API)
        self._copy_pressed_panel = None
        self._pressed_link = None
        if (event.button() == Qt.MouseButton.LeftButton
                and getattr(self, 'highlighter', None) is not None
                and self.highlighter.enabled):
            panel = self.code_panel_at(event.position())
            if panel and self.code_copy_rect(self.code_panel_rect(*panel)).contains(event.position()):
                self._hovered_code_panel = panel
                self._copy_pressed_panel = panel
                self.viewport().update()
                event.accept()
                return
        if (event.button() == Qt.MouseButton.LeftButton
                and event.modifiers() == Qt.KeyboardModifier.NoModifier):
            url = self.web_link_at_position(event.position())
            if url:
                self._pressed_link = (url, event.position())
        super().mousePressEvent(event)
        block = self.textCursor().block()
        if block.userState() in (2, 3, 4):
            self._table_edit_position = block.position()
            self.highlighter.rehighlightBlock(block)
            self.viewport().update()

    def mouseReleaseEvent(self, event):  # noqa: N802 (Qt API)
        panel = self._copy_pressed_panel
        self._copy_pressed_panel = None
        pressed_link = self._pressed_link
        self._pressed_link = None
        if panel is not None and event.button() == Qt.MouseButton.LeftButton:
            start, end = panel
            if self.code_copy_rect(self.code_panel_rect(start, end)).contains(event.position()):
                block = self.document().findBlock(start).next()
                lines = []
                while block.isValid() and block.position() <= end:
                    if block.position() == end and re.match(
                            r"^\s*(?:`{3,}|~{3,})", block.text()):
                        break
                    lines.append(block.text())
                    block = block.next()
                clipboard = QApplication.clipboard()
                copied = '\n'.join(lines)
                clipboard.setText(copied, QClipboard.Mode.Clipboard)
                if clipboard.supportsSelection():
                    clipboard.setText(copied, QClipboard.Mode.Selection)
                self.viewport().setToolTip("")
                QToolTip.showText(event.globalPosition().toPoint(), "Copied",
                                  self.viewport(), self.code_copy_rect(
                                      self.code_panel_rect(start, end)).toRect(), 1500)
            event.accept()
            return
        if (pressed_link is not None and event.button() == Qt.MouseButton.LeftButton
                and (event.position() - pressed_link[1]).manhattanLength()
                < QApplication.startDragDistance() and not self.textCursor().hasSelection()):
            QDesktopServices.openUrl(QUrl(pressed_link[0]))
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paint_code_panels(self, painter, dirty):
        highlighter = self.highlighter
        panel_color = QColor(highlighter.theme['md_code_background'])
        base_color = self.palette().color(QPalette.ColorRole.Base)
        icon_color = highlighter.theme['secondary']
        for start, end in self.code_panels:
            panel = self.code_panel_rect(start, end)
            if not panel.intersects(QRectF(dirty)):
                continue
            inset = self.document().documentMargin()
            painter.fillRect(QRectF(panel.left(), panel.top(), inset, panel.height()), panel_color)
            painter.fillRect(QRectF(panel.right() - inset, panel.top(),
                                    inset, panel.height()), panel_color)
            block = self.document().findBlock(start)
            if panel.top() < dirty.top():
                visible = self.cursorForPosition(dirty.topLeft()).block()
                if visible.position() > block.position():
                    block = visible.previous()
            while block.isValid() and block.position() < end:
                next_block = block.next()
                cursor = QTextCursor(block)
                cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
                gap_top = self.cursorRect(cursor).bottom() + 1
                gap_bottom = self.cursorRect(QTextCursor(next_block)).top()
                if gap_top > dirty.bottom():
                    break
                if gap_bottom > gap_top:
                    painter.fillRect(QRectF(panel.left(), gap_top,
                                            panel.width(), gap_bottom - gap_top), panel_color)
                block = next_block
            corners = QPainterPath()
            corners.setFillRule(Qt.FillRule.OddEvenFill)
            corners.addRect(panel)
            corners.addRoundedRect(panel, 8, 8)
            painter.fillPath(corners, base_color)
            if (start, end) == self._hovered_code_panel:
                icon = self.code_copy_rect(panel)
                boxicon("copy", icon_color).render(
                    painter, QRectF(icon.left() + 3, icon.top() + 2, 24, 24))

    def set_max_page_width(self, pixels: int):
        self.max_page_width = pixels
        self.update_page_margins()

    def contextMenuEvent(self, event):  # noqa: N802
        if not hasattr(self, 'spelling'):
            return super().contextMenuEvent(event)
        menu = self.spelling.context_menu(event.pos())
        menu.exec(event.globalPos())
        menu.deleteLater()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self.update_page_margins()
        self.schedule_code_panel_update()

    def update_page_margins(self):
        margins = self.viewportMargins()
        available = self.viewport().width() + margins.left() + margins.right()
        extra = max(0, available - 52 - self.max_page_width) if self.max_page_width else 0
        left, right = 26 + extra // 2, 26 + (extra + 1) // 2
        if margins.left() != left or margins.right() != right:
            self.setViewportMargins(left, 10, right, 10)

    def set_paragraph_spacing(self, pixels: int):
        cursor = self.textCursor()
        formatting_cursor = QTextCursor(self.document())
        formatting_cursor.select(QTextCursor.SelectionType.Document)
        block_format = QTextBlockFormat()
        block_format.setBottomMargin(pixels)
        was_modified = self.document().isModified()
        formatting_cursor.mergeBlockFormat(block_format)
        self.document().setModified(was_modified)
        self.setTextCursor(cursor)

    def canInsertFromMimeData(self, source):  # noqa: N802
        return source.hasUrls() or super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):  # noqa: N802
        if source.hasUrls():
            paths = [url.toLocalFile() for url in source.urls() if url.isLocalFile()]
            if paths:
                self.files_dropped.emit(paths)
                return
        super().insertFromMimeData(source)


class BoxIconButton(QToolButton):
    """Paint a bundled Boxicons SVG in the active theme color."""

    def __init__(self, icon_name, parent=None):
        super().__init__(parent)
        self.icon_name = icon_name

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        theme = self.window().theme
        color = (theme['disabled'] if not self.isEnabled() else
                 theme['window'] if self.objectName() == "closeControl" and self.underMouse() else
                 theme['text'])
        if self.icon_name == "sidebar":
            painter.translate(self.width(), 0)
            painter.scale(-1, 1)
        boxicon(self.icon_name, color).render(
            painter, QRectF((self.width() - 18) / 2, (self.height() - 18) / 2, 18, 18))


class WindowMenuBar(QMenuBar):
    """Allow the empty part of the menu row to move or maximize the window."""

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self.position_title()

    def position_title(self):
        if not hasattr(self, "title_label"):
            return
        center = self.width() // 2
        menus_end = self.actionGeometry(self.actions()[-1]).right() + 14
        controls = self.cornerWidget(Qt.Corner.TopRightCorner)
        controls_start = self.width() - controls.width() - 14 if controls else self.width() - 14
        width = max(0, min(280, 2 * min(center - menus_end, controls_start - center)))
        self.title_label.setGeometry(center - width // 2, 0, width, self.height())
        self.title_label.setText(self.title_label.fontMetrics().elidedText(
            self.title_label.toolTip(), Qt.TextElideMode.ElideMiddle, width
        ))
        self.title_label.setVisible(width > 20)

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.actionAt(event.pos()) is None:
            if self.window().windowHandle().startSystemMove():
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.actionAt(event.pos()) is None:
            self.window().toggle_maximize()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class MainWindow(QMainWindow):
    def __init__(self, initial_file: Path | None = None):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        menu_bar = WindowMenuBar(self)
        menu_bar.setNativeMenuBar(False)
        self.setMenuBar(menu_bar)
        self.settings = QSettings("Pad", "Pad")
        app = QApplication.instance()
        if not hasattr(app, 'pad_system_palette'):
            app.pad_system_palette = QPalette(app.palette())
            app.setStyle('Fusion')
        self.theme_id = saved_theme_id(self.settings)
        self.theme = resolve_theme(self.theme_id, app.pad_system_palette)
        self.font_size = max(MIN_FONT_SIZE, min(MAX_FONT_SIZE,
            self.settings.value("font_size", DEFAULT_FONT_SIZE, type=int)))
        self.paragraph_spacing = max(0, min(48, self.settings.value("paragraph_spacing", 14, type=int)))
        self.max_page_width = max(0, min(10000, self.settings.value("max_page_width", 950, type=int)))
        self.current_file: Path | None = None
        self.newline = "\n"
        self.has_bom = False
        self.loading = False
        self.setWindowTitle(APP_NAME)
        self.resize(1120, 760)
        self.setMinimumSize(640, 440)

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root)

        self.editor = NoteEditor()
        self.editor.setObjectName("editor")
        self.editor.setFont(QFont("Noto Sans", self.font_size))
        self.editor.setTabStopDistance(self.editor.fontMetrics().horizontalAdvance(" ") * 4)
        self.editor.set_paragraph_spacing(self.paragraph_spacing)
        self.editor.set_max_page_width(self.max_page_width)
        self.content_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.content_splitter.setObjectName("contentSplitter")
        self.content_splitter.setHandleWidth(6)
        self.content_splitter.setChildrenCollapsible(False)
        self.editor.setMinimumWidth(280)
        self.content_splitter.addWidget(self.editor)
        self.heading_panel = QWidget()
        self.heading_panel.setObjectName("headingPanel")
        self.heading_panel.setMinimumWidth(1)
        panel_layout = QVBoxLayout(self.heading_panel)
        panel_layout.setContentsMargins(12, 16, 12, 12)
        self.heading_list = QListWidget()
        self.heading_list.setObjectName("headingList")
        self.heading_list.setAccessibleName("Document headings")
        self.heading_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.heading_list.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.heading_list.itemClicked.connect(self.go_to_heading)
        self.heading_list.itemActivated.connect(self.go_to_heading)
        panel_layout.addWidget(self.heading_list)
        self.content_splitter.addWidget(self.heading_panel)
        self.content_splitter.setStretchFactor(0, 1)
        self.content_splitter.setStretchFactor(1, 0)
        self.content_splitter.resize(self.width(), self.height())
        self.heading_panel_expanded_width = max(140, self.settings.value("heading_panel_width", 240, type=int))
        self.heading_panel_state = self.settings.value("heading_panel_state", "narrow")
        if self.heading_panel_state not in ("narrow", "full", "closed"):
            self.heading_panel_state = "narrow"
        self._resizing_heading_panel = False
        self.content_splitter.setSizes([self.width() - self.heading_panel_expanded_width - 6,
                                        self.heading_panel_expanded_width])
        self.content_splitter.handle(1).setToolTip("Drag to resize the headings panel")
        self.content_splitter.handle(1).setEnabled(self.heading_panel_state == "full")
        root_layout.addWidget(self.content_splitter, 1)
        self.heading_panel.hide()
        self.content_splitter.splitterMoved.connect(self.remember_heading_panel_width)
        self.headings = []

        self.find_footer = QWidget()
        self.find_footer.setObjectName("findFooter")
        find_layout = QHBoxLayout(self.find_footer)
        find_layout.setContentsMargins(18, 7, 18, 7)
        find_layout.setSpacing(8)
        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText("Search text")
        self.find_input.setAccessibleName("Find text")
        self.find_input.setClearButtonEnabled(True)
        self.find_input.setMaximumWidth(360)
        self.find_input.textChanged.connect(self.update_find_matches)
        self.find_input.returnPressed.connect(lambda: self.move_find_match(1))
        self.find_input.installEventFilter(self)
        find_layout.addWidget(self.find_input, 1)
        self.find_match_case = QToolButton()
        self.find_match_case.setText("Aa")
        self.find_match_case.setCheckable(True)
        self.find_match_case.setToolTip("Match case")
        self.find_match_case.setAccessibleName("Match case")
        self.find_match_case.toggled.connect(self.update_find_matches)
        find_layout.addWidget(self.find_match_case)
        self.find_whole_word = QToolButton()
        self.find_whole_word.setText("|ab|")
        self.find_whole_word.setCheckable(True)
        self.find_whole_word.setToolTip("Match whole word")
        self.find_whole_word.setAccessibleName("Match whole word")
        self.find_whole_word.toggled.connect(self.update_find_matches)
        find_layout.addWidget(self.find_whole_word)
        self.find_count = QLabel("0 matches")
        self.find_count.setObjectName("findCount")
        find_layout.addWidget(self.find_count)
        self.find_previous = BoxIconButton("up-arrow-alt")
        self.find_previous.setToolTip("Previous match")
        self.find_previous.setAccessibleName("Previous match")
        self.find_previous.clicked.connect(lambda: self.move_find_match(-1))
        find_layout.addWidget(self.find_previous)
        self.find_next = BoxIconButton("down-arrow-alt")
        self.find_next.setToolTip("Next match")
        self.find_next.setAccessibleName("Next match")
        self.find_next.clicked.connect(lambda: self.move_find_match(1))
        find_layout.addWidget(self.find_next)
        close_find = BoxIconButton("x")
        close_find.setToolTip("Close Find")
        close_find.setAccessibleName("Close Find")
        close_find.clicked.connect(self.close_find)
        find_layout.addWidget(close_find)
        root_layout.addWidget(self.find_footer)
        self.find_footer.hide()

        self.replace_footer = QWidget()
        self.replace_footer.setObjectName("replaceFooter")
        replace_layout = QHBoxLayout(self.replace_footer)
        replace_layout.setContentsMargins(10, 7, 10, 7)
        replace_layout.setSpacing(4)
        self.replace_search_input = QLineEdit()
        self.replace_search_input.setPlaceholderText("Search text")
        self.replace_search_input.setAccessibleName("Replace search text")
        self.replace_search_input.setClearButtonEnabled(True)
        self.replace_search_input.setMaximumWidth(360)
        self.replace_search_input.setMinimumWidth(80)
        self.replace_search_input.textChanged.connect(self.update_find_matches)
        self.replace_search_input.returnPressed.connect(lambda: self.move_find_match(1))
        self.replace_search_input.installEventFilter(self)
        replace_layout.addWidget(self.replace_search_input, 1)
        self.replace_match_case = QToolButton()
        self.replace_match_case.setText("Aa")
        self.replace_match_case.setCheckable(True)
        self.replace_match_case.setToolTip("Match case")
        self.replace_match_case.setAccessibleName("Replace match case")
        self.replace_match_case.toggled.connect(self.update_find_matches)
        replace_layout.addWidget(self.replace_match_case)
        self.replace_whole_word = QToolButton()
        self.replace_whole_word.setText("|ab|")
        self.replace_whole_word.setCheckable(True)
        self.replace_whole_word.setToolTip("Match whole word")
        self.replace_whole_word.setAccessibleName("Replace match whole word")
        self.replace_whole_word.toggled.connect(self.update_find_matches)
        replace_layout.addWidget(self.replace_whole_word)
        self.replace_count = QLabel("0 matches")
        self.replace_count.setObjectName("replaceCount")
        replace_layout.addWidget(self.replace_count)
        self.replace_previous = BoxIconButton("up-arrow-alt")
        self.replace_previous.setToolTip("Previous match")
        self.replace_previous.setAccessibleName("Previous match")
        self.replace_previous.clicked.connect(lambda: self.move_find_match(-1))
        replace_layout.addWidget(self.replace_previous)
        self.replace_next = BoxIconButton("down-arrow-alt")
        self.replace_next.setToolTip("Next match")
        self.replace_next.setAccessibleName("Next match")
        self.replace_next.clicked.connect(lambda: self.move_find_match(1))
        replace_layout.addWidget(self.replace_next)
        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText("Replacement text")
        self.replace_input.setAccessibleName("Replacement text")
        self.replace_input.setClearButtonEnabled(True)
        self.replace_input.setMaximumWidth(360)
        self.replace_input.setMinimumWidth(80)
        self.replace_input.installEventFilter(self)
        replace_layout.addWidget(self.replace_input, 1)
        self.replace_next_button = BoxIconButton("right-arrow-alt")
        self.replace_next_button.setToolTip("Replace current match")
        self.replace_next_button.setAccessibleName("Replace current match")
        self.replace_next_button.clicked.connect(self.replace_current_match)
        replace_layout.addWidget(self.replace_next_button)
        self.replace_all_button = BoxIconButton("chevrons-right")
        self.replace_all_button.setToolTip("Replace all matches")
        self.replace_all_button.setAccessibleName("Replace all matches")
        self.replace_all_button.clicked.connect(self.replace_all_matches)
        replace_layout.addWidget(self.replace_all_button)
        close_replace = BoxIconButton("x")
        close_replace.setToolTip("Close Replace")
        close_replace.setAccessibleName("Close Replace")
        close_replace.clicked.connect(self.close_replace)
        replace_layout.addWidget(close_replace)
        root_layout.addWidget(self.replace_footer)
        self.replace_footer.hide()
        self.find_matches = []
        self.find_index = -1

        status = QWidget()
        status.setObjectName("status")
        status_layout = QHBoxLayout(status)
        status_layout.setContentsMargins(18, 6, 18, 6)
        self.count_label = QLabel("0 words")
        status_layout.addStretch(1)
        status_layout.addWidget(self.count_label)
        root_layout.addWidget(status)

        self.highlighter = MarkdownHighlighter(self.editor.document(), self.theme, self.editor)
        self.editor.spelling = Spelling(self.editor, self.settings, self.highlighter)
        self.apply_theme()
        self.setup_actions()
        QApplication.instance().installEventFilter(self)
        self.editor.textChanged.connect(self.on_text_changed)
        self.editor.cursorPositionChanged.connect(self.update_find_position)
        self.editor.document().modificationChanged.connect(self.update_title)
        self.editor.files_dropped.connect(self.open_dropped)
        self.editor.document().setModified(False)
        self.editor.document().clearUndoRedoStacks()
        if initial_file:
            self.open_file(initial_file)
        self.editor.setFocus()

    def apply_theme(self):
        app = QApplication.instance()
        self.theme = resolve_theme(self.theme_id, app.pad_system_palette)
        # Rehighlighting changes layout formats only, preserving undo and source.
        vertical = self.editor.verticalScrollBar().value()
        horizontal = self.editor.horizontalScrollBar().value()
        modified = self.editor.document().isModified()
        was_loading = self.loading
        self.loading = True
        try:
            apply_application_theme(app, self.theme)
            self.highlighter.update_colors(self.theme)
            self.editor.spelling.color = QColor(self.theme['error'])
            self.editor.spelling.refresh()
            self.refresh_find_selections()
            self.editor.document().setModified(modified)
        finally:
            self.loading = was_loading
        self.editor.verticalScrollBar().setValue(vertical)
        self.editor.horizontalScrollBar().setValue(horizontal)

    def set_theme(self, identifier):
        if identifier not in THEMES and identifier != 'system':
            return
        self.theme_id = identifier
        self.apply_theme()
        self.settings.setValue('theme', identifier)
        self.settings.sync()

    def create_appearance_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Themes')
        dialog.setMinimumWidth(440)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        label = QLabel('Theme')
        font = label.font()
        font.setBold(True)
        label.setFont(font)
        layout.addWidget(label)
        group = QButtonGroup(dialog)
        for theme in (*THEMES.values(), resolve_theme('system', QApplication.instance().pad_system_palette)):
            choice = QRadioButton(theme.name)
            choice.setObjectName(theme.id)
            choice.setAccessibleDescription(theme.description)
            choice.setChecked(self.theme_id == theme.id)
            group.addButton(choice)
            choice.toggled.connect(lambda checked, identifier=theme.id: self.set_theme(identifier) if checked else None)
            layout.addWidget(choice)
            preview = QLabel("<b># A quiet place to write</b><br>The next chapter begins here…")
            preview.setAccessibleName(theme.name + ' color preview')
            preview.setStyleSheet(f"background: {theme['editor']}; color: {theme['text']}; "
                                 f"border-left: 3px solid {theme['accent']}; padding: 10px;")
            layout.addWidget(preview)
            description = QLabel(theme.description)
            layout.addWidget(description)
        hint = QLabel('Changes apply immediately and are saved automatically.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dialog)
        buttons.rejected.connect(dialog.close)
        layout.addWidget(buttons)
        return dialog

    def show_appearance(self):
        dialog = self.create_appearance_dialog()
        dialog.exec()
        dialog.deleteLater()

    def setup_actions(self):
        menu = self.menuBar().addMenu("File")
        actions = [
            ("New", QKeySequence.StandardKey.New, self.new_file),
            ("Open…", QKeySequence.StandardKey.Open, self.choose_file),
            ("Save", QKeySequence.StandardKey.Save, self.save_file),
            ("Save as…", QKeySequence.StandardKey.SaveAs, self.save_as),
        ]
        for label, shortcut, callback in actions:
            action = QAction(label, self)
            action.setShortcut(shortcut)
            action.triggered.connect(callback)
            menu.addAction(action)
            self.addAction(action)
            if shortcut == QKeySequence.StandardKey.Open:
                self.recent_menu = menu.addMenu("Open Recent")
                self.recent_menu.aboutToShow.connect(self.update_recent_menu)
                self.update_recent_menu()
        menu.addSeparator()
        find_action = QAction("Find", self)
        find_action.setShortcut(QKeySequence.StandardKey.Find)
        find_action.triggered.connect(self.open_find)
        menu.addAction(find_action)
        self.addAction(find_action)
        replace_action = QAction("Replace", self)
        replace_action.setShortcut(QKeySequence("Ctrl+R"))
        replace_action.triggered.connect(self.open_replace)
        menu.addAction(replace_action)
        self.addAction(replace_action)
        menu.addSeparator()
        remove_extra_action = QAction("Remove Extra ↵", self)
        remove_extra_action.triggered.connect(self.remove_extra_newlines)
        menu.addAction(remove_extra_action)
        remove_spaces_action = QAction("Remove Extra Spaces", self)
        remove_spaces_action.triggered.connect(self.remove_extra_spaces)
        menu.addAction(remove_spaces_action)
        menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        menu.addAction(quit_action)
        self.addAction(quit_action)
        settings_menu = self.menuBar().addMenu("Settings")
        settings_menu.addAction("Themes…", self.show_appearance)
        settings_menu.addAction("Updates…", self.show_updates)
        self.spell_check_action = QAction("Spell check (English)", self)
        self.spell_check_action.setCheckable(True)
        self.spell_check_action.setChecked(self.editor.spelling.enabled)
        self.spell_check_action.toggled.connect(self.editor.spelling.set_enabled)
        settings_menu.addAction(self.spell_check_action)
        settings_menu.addSeparator()
        font_action = QAction("Font size…", self)
        font_action.triggered.connect(self.show_font_size)
        settings_menu.addAction(font_action)
        for label, shortcuts, delta in (
            ("Increase font size", ["Ctrl++", "Ctrl+=", "Ctrl+Shift++"], 1),
            ("Decrease font size", ["Ctrl+-"], -1),
        ):
            action = QAction(label, self)
            action.setShortcuts([QKeySequence(shortcut) for shortcut in shortcuts])
            action.triggered.connect(
                lambda checked=False, step=delta: self.set_font_size(self.font_size + step)
            )
            settings_menu.addAction(action)
            self.addAction(action)
        settings_menu.addSeparator()
        spacing_action = QAction("Paragraph spacing…", self)
        spacing_action.triggered.connect(self.show_paragraph_spacing)
        settings_menu.addAction(spacing_action)
        width_action = QAction("Max Page Width…", self)
        width_action.triggered.connect(self.show_max_page_width)
        settings_menu.addAction(width_action)
        panel_menu = settings_menu.addMenu("Heading panel")
        self.heading_state_actions = {}
        heading_state_group = QActionGroup(self)
        for state, label in (("narrow", "Narrow"), ("full", "Full"), ("closed", "Closed")):
            action = panel_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(state == self.heading_panel_state)
            action.triggered.connect(lambda checked=False, selected=state: self.set_heading_panel_state(selected))
            heading_state_group.addAction(action)
            self.heading_state_actions[state] = action
        controls = QWidget(self.menuBar())
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(0)
        self.heading_button = BoxIconButton("sidebar", controls)
        self.minimize_button = BoxIconButton("minus", controls)
        self.maximize_button = BoxIconButton("square", controls)
        self.close_button = BoxIconButton("x", controls)
        for button in (self.heading_button, self.minimize_button, self.maximize_button, self.close_button):
            button.setObjectName("closeControl" if button is self.close_button else "windowControl")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setAutoRaise(True)
            controls_layout.addWidget(button)
        self.heading_button.setAccessibleName("Cycle heading panel state")
        self.heading_button.clicked.connect(self.cycle_heading_panel_state)
        self.update_heading_button_tooltip()
        self.heading_button.hide()
        self.minimize_button.setToolTip("Minimize")
        self.maximize_button.setToolTip("Maximize")
        self.close_button.setToolTip("Close")
        self.update_maximize_button()
        self.minimize_button.clicked.connect(self.showMinimized)
        self.maximize_button.clicked.connect(self.toggle_maximize)
        self.close_button.clicked.connect(self.close)
        self.menuBar().setCornerWidget(controls, Qt.Corner.TopRightCorner)
        self.title_label = QLabel("Untitled", self.menuBar())
        self.title_label.setObjectName("title")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setToolTip("Untitled")
        self.menuBar().title_label = self.title_label
        self.menuBar().position_title()

    def cycle_heading_panel_state(self):
        states = ("narrow", "full", "closed")
        self.set_heading_panel_state(states[(states.index(self.heading_panel_state) + 1) % len(states)])

    def update_heading_button_tooltip(self):
        next_state = {"narrow": "Full", "full": "Closed", "closed": "Narrow"}[self.heading_panel_state]
        self.heading_button.setToolTip(f"Heading panel: {self.heading_panel_state.title()} (click for {next_state})")

    def set_heading_panel_state(self, state):
        if state not in ("narrow", "full", "closed"):
            raise ValueError(f"Unknown heading panel state: {state}")
        self.heading_panel_state = state
        self.settings.setValue("heading_panel_state", state)
        self.heading_state_actions[state].setChecked(True)
        self.update_heading_button_tooltip()
        self.heading_panel.setVisible(state != "closed" and len(self.headings) > 1)
        self.content_splitter.handle(1).setEnabled(state == "full")
        self.update_heading_panel_display()

    def remember_heading_panel_width(self, _position, _index):
        if self.heading_panel_state == "full" and self.heading_panel.isVisible() and not self._resizing_heading_panel:
            self.heading_panel_expanded_width = self.content_splitter.sizes()[1]
            self.settings.setValue("heading_panel_width", self.heading_panel_expanded_width)

    def heading_panel_compact_width(self):
        labels = [title[:3] for _, _, title in self.headings]
        text_width = max((self.heading_list.fontMetrics().horizontalAdvance(label)
                          for label in labels), default=0)
        margins = self.heading_panel.layout().contentsMargins()
        return (text_width + margins.left() + margins.right() + 8
                + self.heading_list.verticalScrollBar().sizeHint().width())

    def update_heading_panel_display(self):
        expanded = self.heading_panel_state == "full"
        for item, (_, level, title) in zip(
                (self.heading_list.item(i) for i in range(self.heading_list.count())), self.headings):
            item.setText("  " * (level - 1) + title if expanded else title[:3])
        if self.heading_panel.isVisible():
            width = self.heading_panel_expanded_width if expanded else self.heading_panel_compact_width()
            self.resize_heading_panel(width)

    def resize_heading_panel(self, width):
        self._resizing_heading_panel = True
        try:
            self.content_splitter.setSizes([max(280, self.content_splitter.width() - int(width) - 6), int(width)])
        finally:
            self._resizing_heading_panel = False

    def update_headings(self, reset=False):
        headings = []
        if self.highlighter.enabled:
            in_code = False
            block = self.editor.document().firstBlock()
            while block.isValid():
                text = block.text()
                if re.match(r"^\s*(`{3,}|~{3,})", text):
                    in_code = not in_code
                elif not in_code:
                    match = re.match(r"^(#{1,6})\s+(.*)$", text)
                    if match:
                        title = re.sub(r"\s+#+\s*$", "", match.group(2)).strip()
                        headings.append((block.position(), len(match.group(1)), title or "Untitled heading"))
                block = block.next()
        was_available = len(self.headings) > 1
        available = len(headings) > 1
        if headings != self.headings or reset:
            scroll = self.heading_list.verticalScrollBar().value()
            self.heading_list.clear()
            for position, level, title in headings:
                item = QListWidgetItem("  " * (level - 1) + title if self.heading_panel_state == "full" else title[:3])
                item.setToolTip(title)
                item.setData(Qt.ItemDataRole.UserRole, position)
                self.heading_list.addItem(item)
            self.heading_list.verticalScrollBar().setValue(0 if reset else scroll)
            self.headings = headings
            if available and self.heading_panel.isVisible() and not reset:
                self.update_heading_panel_display()
        self.heading_button.setVisible(available)
        self.heading_panel.setVisible(available and self.heading_panel_state != "closed")
        if available and (reset or not was_available):
            self.update_heading_panel_display()
        self.menuBar().position_title()

    def go_to_heading(self, item):
        cursor = QTextCursor(self.editor.document())
        cursor.setPosition(item.data(Qt.ItemDataRole.UserRole))
        self.editor.setTextCursor(cursor)
        self.editor.ensureCursorVisible()
        self.editor.setFocus()

    def remove_extra_newlines(self):
        document = self.editor.document()
        positions = []
        block = document.firstBlock().next()
        while block.isValid() and block.next().isValid():
            if not block.text():
                positions.append(block.position())
            block = block.next()
        if not positions:
            return

        cursor = QTextCursor(document)
        cursor.beginEditBlock()
        for position in reversed(positions):
            cursor.setPosition(position - 1)
            cursor.setPosition(position, QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
        cursor.endEditBlock()

    def remove_extra_spaces(self):
        document = self.editor.document()
        ranges = []
        block = document.firstBlock()
        while block.isValid():
            text = block.text()
            for match in re.finditer(r" +", text):
                beside_newline = (
                    (match.start() == 0 and block.previous().isValid())
                    or (match.end() == len(text) and block.next().isValid())
                )
                start = match.start() + (0 if beside_newline else 1)
                if start < match.end():
                    # Qt cursor positions count UTF-16 units, including for emoji.
                    position = block.position() + len(text[:start].encode("utf-16-le")) // 2
                    ranges.append((position, match.end() - start))
            block = block.next()
        if not ranges:
            return

        cursor = QTextCursor(document)
        cursor.beginEditBlock()
        for position, length in reversed(ranges):
            cursor.setPosition(position)
            cursor.setPosition(position + length, QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
        cursor.endEditBlock()

    def show_font_size(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Font size")
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        size = QSpinBox(dialog)
        size.setRange(MIN_FONT_SIZE, MAX_FONT_SIZE)
        size.setSuffix(" pt")
        size.setValue(self.font_size)
        size.valueChanged.connect(self.set_font_size)
        form.addRow("Font size:", size)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dialog)
        buttons.rejected.connect(dialog.close)
        layout.addWidget(buttons)
        dialog.exec()

    def set_font_size(self, points: int):
        self.font_size = max(MIN_FONT_SIZE, min(MAX_FONT_SIZE, points))
        font = self.editor.font()
        font.setPointSize(self.font_size)
        self.editor.setFont(font)
        self.editor.setTabStopDistance(self.editor.fontMetrics().horizontalAdvance(" ") * 4)
        self.highlighter.rehighlight()
        self.settings.setValue("font_size", self.font_size)

    def show_paragraph_spacing(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Paragraph spacing")
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        spacing = QSpinBox(dialog)
        spacing.setRange(0, 48)
        spacing.setSuffix(" px")
        spacing.setValue(self.paragraph_spacing)
        spacing.valueChanged.connect(self.set_paragraph_spacing)
        form.addRow("Space after each paragraph:", spacing)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dialog)
        buttons.rejected.connect(dialog.close)
        layout.addWidget(buttons)
        dialog.exec()

    def show_max_page_width(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Max Page Width")
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        width = QSpinBox(dialog)
        width.setRange(0, 10000)
        width.setSingleStep(50)
        width.setSuffix(" px")
        width.setSpecialValueText("Unlimited")
        width.setValue(self.max_page_width)
        width.valueChanged.connect(self.set_max_page_width)
        form.addRow("Max Page Width:", width)
        layout.addLayout(form)
        hint = QLabel("Centers the text page in wider windows. Set to 0 for unlimited width.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dialog)
        buttons.rejected.connect(dialog.close)
        layout.addWidget(buttons)
        dialog.exec()

    def set_max_page_width(self, pixels: int):
        self.max_page_width = pixels
        self.settings.setValue("max_page_width", pixels)
        self.editor.set_max_page_width(pixels)

    def set_paragraph_spacing(self, pixels: int):
        self.paragraph_spacing = pixels
        self.settings.setValue("paragraph_spacing", pixels)
        self.editor.set_paragraph_spacing(pixels)
        self.update_title()
        self.update_status()

    def update_maximize_button(self):
        maximized = self.isMaximized()
        self.maximize_button.icon_name = "windows" if maximized else "square"
        self.maximize_button.update()
        self.maximize_button.setToolTip("Restore" if maximized else "Maximize")

    def toggle_maximize(self):
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def changeEvent(self, event):  # noqa: N802
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, "maximize_button"):
            self.update_maximize_button()
        super().changeEvent(event)

    def eventFilter(self, watched, event):  # noqa: N802
        if watched in (self.find_input, getattr(self, 'replace_search_input', None),
                       getattr(self, 'replace_input', None)) \
                and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self.close_replace() if self.replace_footer.isVisible() else self.close_find()
                return True
            if (watched is not self.replace_input
                    and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                    and event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
                self.move_find_match(-1)
                return True
        if (event.type() == QEvent.Type.MouseButtonDblClick
                and event.button() == Qt.MouseButton.LeftButton
                and watched is self.title_label):
            self.toggle_maximize()
            return True
        if (event.type() == QEvent.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.LeftButton
                and isinstance(watched, QWidget)
                and watched.window() is self):
            if not self.isMaximized():
                point = self.mapFromGlobal(event.globalPosition().toPoint())
                edge = Qt.Edge(0)
                if point.x() < 6:
                    edge |= Qt.Edge.LeftEdge
                elif point.x() >= self.width() - 6:
                    edge |= Qt.Edge.RightEdge
                if point.y() < 6:
                    edge |= Qt.Edge.TopEdge
                elif point.y() >= self.height() - 6:
                    edge |= Qt.Edge.BottomEdge
                if edge and self.windowHandle() and self.windowHandle().startSystemResize(edge):
                    return True
            if watched is self.title_label:
                if self.windowHandle() and self.windowHandle().startSystemMove():
                    return True
        return super().eventFilter(watched, event)

    def update_recent_menu(self):
        self.recent_menu.clear()
        paths = self.settings.value("recent_files", [], type=list)
        if not paths:
            self.recent_menu.addAction("No recent files").setEnabled(False)
            return
        for filename in paths[:MAX_RECENT_FILES]:
            action = self.recent_menu.addAction(filename.replace("&", "&&"))
            action.setToolTip(filename)
            action.triggered.connect(
                lambda checked=False, path=filename: self.open_file(Path(path))
            )
        self.recent_menu.addSeparator()
        self.recent_menu.addAction("Clear Recent", self.clear_recent_files)

    def remember_recent_file(self, path: Path):
        filename = str(path.resolve())
        paths = self.settings.value("recent_files", [], type=list)
        paths = [filename] + [entry for entry in paths if entry != filename]
        self.settings.setValue("recent_files", paths[:MAX_RECENT_FILES])

    def clear_recent_files(self):
        self.settings.remove("recent_files")

    def open_dropped(self, paths: list[str]):
        for filename in paths:
            path = Path(filename)
            if path.is_file():
                self.open_file(path)
                break

    def choose_file(self):
        selected, _ = QFileDialog.getOpenFileName(
            self, "Open note", str(self.current_file.parent if self.current_file else Path.home()), FILE_FILTER,
            options=QFileDialog.Option.DontUseNativeDialog
        )
        if selected:
            self.open_file(Path(selected))

    def open_file(self, path: Path):
        if not self.confirm_discard():
            return False
        try:
            raw = path.read_bytes()
            content = raw.decode("utf-8-sig")
        except (OSError, UnicodeError) as exc:
            QMessageBox.critical(self, "Could not open file", f"{path}\n\n{exc}")
            return False
        self.has_bom = raw.startswith(codecs.BOM_UTF8)
        self.newline = "\r\n" if "\r\n" in content else ("\r" if "\r" in content else "\n")
        content = content.replace("\r\n", "\n").replace("\r", "\n")
        self.loading = True
        self.editor.setPlainText(content)
        self.editor.set_paragraph_spacing(self.paragraph_spacing)
        self.loading = False
        self.current_file = path.resolve()
        self.highlighter.enabled = self.current_file.suffix.lower() != ".txt"
        self.highlighter.rehighlight()
        self.editor.update_code_panels()
        self.editor.document().setModified(False)
        self.editor.document().clearUndoRedoStacks()
        self.editor.moveCursor(self.editor.textCursor().MoveOperation.Start)
        self.update_headings(reset=True)
        self.update_title()
        self.update_status()
        self.editor.setFocus()
        self.remember_recent_file(self.current_file)
        return True

    def new_file(self):
        if not self.confirm_discard():
            return
        self.loading = True
        self.editor.clear()
        self.editor.set_paragraph_spacing(self.paragraph_spacing)
        self.loading = False
        self.current_file = None
        self.newline = "\n"
        self.has_bom = False
        self.highlighter.enabled = True
        self.highlighter.rehighlight()
        self.editor.update_code_panels()
        self.editor.document().setModified(False)
        self.editor.document().clearUndoRedoStacks()
        self.update_title()
        self.update_status()
        self.editor.setFocus()

    def confirm_discard(self) -> bool:
        if not self.editor.document().isModified():
            return True
        name = self.current_file.name if self.current_file else "Untitled"
        choice = QMessageBox.question(
            self, "Unsaved changes", f"Save changes to {name}?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if choice == QMessageBox.StandardButton.Cancel:
            return False
        if choice == QMessageBox.StandardButton.Save:
            return self.save_file()
        return True

    def save_file(self) -> bool:
        if self.current_file is None:
            return self.save_as()
        output = QSaveFile(str(self.current_file))
        if not output.open(QSaveFile.OpenModeFlag.WriteOnly):
            QMessageBox.critical(self, "Could not save file", f"{self.current_file}\n\n{output.errorString()}")
            return False
        content = self.editor.toPlainText().replace("\n", self.newline).encode("utf-8")
        if self.has_bom:
            content = codecs.BOM_UTF8 + content
        if output.write(content) != len(content) or not output.commit():
            error = output.errorString()
            output.cancelWriting()
            QMessageBox.critical(self, "Could not save file", f"{self.current_file}\n\n{error}")
            return False
        self.editor.document().setModified(False)
        self.highlighter.enabled = self.current_file.suffix.lower() != ".txt"
        self.highlighter.rehighlight()
        self.editor.update_code_panels()
        self.update_title()
        self.update_status()
        self.remember_recent_file(self.current_file)
        return True

    def save_as(self) -> bool:
        start = str(self.current_file or Path.home() / "Untitled.md")
        selected, chosen_filter = QFileDialog.getSaveFileName(self, "Save note", start, FILE_FILTER,
            options=QFileDialog.Option.DontUseNativeDialog)
        if not selected:
            return False
        path = Path(selected)
        if not path.suffix and chosen_filter != "All files (*)":
            path = path.with_suffix(".txt" if chosen_filter == "Text (*.txt)" else ".md")
        previous = self.current_file
        self.current_file = path.resolve()
        if not self.save_file():
            self.current_file = previous
            return False
        return True

    def on_text_changed(self):
        if self.find_footer.isVisible() or self.replace_footer.isVisible():
            self.update_find_matches()
        if not self.loading:
            self.update_title()
            self.update_status()

    def open_find(self):
        if self.find_footer.isVisible():
            self.close_find()
            return
        self.replace_footer.hide()
        self.find_footer.show()
        self.update_find_matches()
        self.find_input.setFocus()
        self.find_input.selectAll()

    def open_replace(self):
        if self.replace_footer.isVisible():
            self.close_replace()
            return
        self.find_footer.hide()
        self.replace_footer.show()
        self.update_find_matches()
        self.replace_search_input.setFocus()
        self.replace_search_input.selectAll()

    def close_find(self):
        self.find_footer.hide()
        self.clear_search_highlights()

    def close_replace(self):
        self.replace_footer.hide()
        self.clear_search_highlights()

    def clear_search_highlights(self):
        self.find_matches = []
        self.find_index = -1
        self.editor._find_selections = []
        self.editor.refresh_extra_selections()
        self.editor.setFocus()

    def search_controls(self):
        if self.replace_footer.isVisible():
            return (self.replace_search_input, self.replace_match_case,
                    self.replace_whole_word, self.replace_count,
                    self.replace_previous, self.replace_next)
        if self.find_footer.isVisible():
            return (self.find_input, self.find_match_case, self.find_whole_word,
                    self.find_count, self.find_previous, self.find_next)
        return None

    def update_find_matches(self):
        self.find_matches = []
        controls = self.search_controls()
        query = controls[0].text() if controls else ""
        if query:
            document = self.editor.document()
            flags = QTextDocument.FindFlag(0)
            if controls[1].isChecked():
                flags |= QTextDocument.FindFlag.FindCaseSensitively
            if controls[2].isChecked():
                flags |= QTextDocument.FindFlag.FindWholeWords
            cursor = document.find(query, 0, flags)
            while not cursor.isNull():
                self.find_matches.append((cursor.selectionStart(), cursor.selectionEnd()))
                cursor = document.find(query, cursor, flags)
        position = self.editor.textCursor().position()
        self.find_index = max((i for i, (start, _) in enumerate(self.find_matches)
                               if start <= position), default=0) if self.find_matches else -1
        self.refresh_find_selections()

    def update_find_position(self):
        if not self.search_controls() or not self.find_matches:
            return
        position = self.editor.textCursor().position()
        index = max((i for i, (start, _) in enumerate(self.find_matches)
                     if start <= position), default=0)
        if index != self.find_index:
            self.find_index = index
            self.refresh_find_selections()

    def refresh_find_selections(self):
        selections = []
        for index, (start, end) in enumerate(self.find_matches):
            selection = QTextEdit.ExtraSelection()
            selection.cursor = QTextCursor(self.editor.document())
            selection.cursor.setPosition(start)
            selection.cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            color = QColor(self.theme['search_current'])
            if index != self.find_index:
                color.setAlpha(100)
            selection.format.setBackground(color)
            if index == self.find_index:
                selection.format.setForeground(QColor(self.theme['search_text']))
            selections.append(selection)
        self.editor._find_selections = selections
        self.editor.refresh_extra_selections()
        total = len(self.find_matches)
        controls = self.search_controls()
        if controls:
            controls[3].setText(f"{self.find_index + 1} of {total}" if total else "0 matches")
            controls[4].setEnabled(bool(total))
            controls[5].setEnabled(bool(total))
        self.replace_next_button.setEnabled(bool(total))
        self.replace_all_button.setEnabled(bool(total))

    def move_find_match(self, direction):
        if not self.find_matches:
            return
        self.find_index = (self.find_index + direction) % len(self.find_matches)
        start, _ = self.find_matches[self.find_index]
        cursor = self.editor.textCursor()
        cursor.setPosition(start)
        self.editor.setTextCursor(cursor)
        self.editor.ensureCursorVisible()
        self.refresh_find_selections()

    def replace_current_match(self):
        if not self.replace_footer.isVisible() or not self.find_matches:
            return
        start, end = self.find_matches[self.find_index]
        replacement = self.replace_input.text()
        cursor = QTextCursor(self.editor.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(replacement)
        self.editor.setTextCursor(cursor)
        self.update_find_matches()
        if self.find_matches:
            next_position = cursor.position()
            self.find_index = next((i for i, (match_start, _) in enumerate(self.find_matches)
                                    if match_start >= next_position), 0)
            target = QTextCursor(self.editor.document())
            target.setPosition(self.find_matches[self.find_index][0])
            self.editor.setTextCursor(target)
            self.editor.ensureCursorVisible()
            self.refresh_find_selections()

    def replace_all_matches(self):
        if not self.replace_footer.isVisible() or not self.find_matches:
            return
        replacement = self.replace_input.text()
        cursor = QTextCursor(self.editor.document())
        cursor.beginEditBlock()
        for start, end in reversed(self.find_matches):
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(replacement)
        cursor.endEditBlock()
        self.update_find_matches()

    def update_title(self):
        name = self.current_file.name if self.current_file else "Untitled"
        dirty = self.editor.document().isModified()
        title = name + ("*" if dirty else "")
        self.title_label.setToolTip(title)
        self.menuBar().position_title()
        self.setWindowTitle(("*" if dirty else "") + name + " — " + APP_NAME)

    def update_status(self):
        self.update_headings()
        count = len(self.editor.toPlainText().split())
        self.count_label.setText(f"{count} word{'s' if count != 1 else ''}")

    def closeEvent(self, event):  # noqa: N802
        if getattr(self, "_updating", False) or self.confirm_discard():
            self.settings.sync()
            event.accept()
        else:
            event.ignore()

    def show_updates(self):
        dialog = UpdatesDialog(self)
        dialog.exec()
        dialog.deleteLater()


def main() -> int:
    parser = argparse.ArgumentParser(description="A native Markdown and text notepad")
    parser.add_argument("--version", action="version",
                        version=f"{APP_NAME} {Path(__file__).with_name('VERSION').read_text().strip()}")
    parser.add_argument("file", nargs="?", type=Path, help="note to open")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setDesktopFileName("pad.desktop")
    app.setWindowIcon(QIcon(str(Path(__file__).resolve().with_name("md_pad_icon.svg"))))
    app.pad_system_palette = QPalette(app.palette())
    app.setStyle('Fusion')
    apply_application_theme(app, resolve_theme(saved_theme_id(QSettings('Pad', 'Pad')), app.pad_system_palette))
    window = MainWindow(args.file)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
