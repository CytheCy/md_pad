"""Offline English spelling with display-only underlines and undoable corrections."""
import re

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QTextEdit
from spellchecker import SpellChecker


WORDS = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*", re.UNICODE)
URLS = re.compile(r"(?:https?://|www\.)\S+|[\w.+-]+@[\w.-]+\.[\w-]+")


def prose_words(text, markdown=True):
    """Yield Python offsets, skipping Markdown code and link destinations."""
    excluded = [(m.start(), m.end()) for m in URLS.finditer(text)]
    if markdown:
        fence = None
        offset = 0
        for line in text.splitlines(keepends=True):
            marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
            if fence:
                excluded.append((offset, offset + len(line)))
                if (marker and marker[1][0] == fence[0] and
                        len(marker[1]) >= len(fence) and not line[marker.end():].strip()):
                    fence = None
            elif marker:
                fence = marker[1]
                excluded.append((offset, offset + len(line)))
            elif line.startswith(('    ', '\t')):
                excluded.append((offset, offset + len(line)))
            offset += len(line)
        for pattern in (r"(`+)[^`]*?\1", r"\]\([^\n)]*\)",
                        r"(?m)^ {0,3}\[[^\]\n]+\]:[^\n]*", r"<[^>\n]+>"):
            excluded.extend((m.start(), m.end()) for m in re.finditer(pattern, text))
    excluded.sort()
    index = 0
    for match in WORDS.finditer(text):
        while index < len(excluded) and excluded[index][1] <= match.start():
            index += 1
        if index < len(excluded) and excluded[index][0] < match.end():
            continue
        # Avoid splitting identifiers and words containing numbers.
        before = text[match.start() - 1:match.start()] if match.start() else ''
        after = text[match.end():match.end() + 1]
        if (before and (before.isalnum() or before == '_')) or (after and (after.isalnum() or after == '_')):
            continue
        yield match.start(), match.end(), match.group()


class Spelling(QObject):
    def __init__(self, editor, settings, highlighter):
        super().__init__(editor)
        self.editor = editor
        self.settings = settings
        self.highlighter = highlighter
        self.dictionary = SpellChecker(language='en', distance=1)
        self.personal = set(settings.value('spelling_words', [], type=list))
        self.ignored = set()
        self.enabled = settings.value('spell_check', True, type=bool)
        self.color = QColor('#e06060')
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.refresh)
        editor.textChanged.connect(self.schedule)

    @staticmethod
    def normalize(word):
        return word.replace('’', "'").lower()

    def known(self, word):
        return not self.dictionary.unknown([word])

    def schedule(self):
        if self.enabled:
            self.timer.start()

    def set_enabled(self, enabled):
        self.enabled = enabled
        self.settings.setValue('spell_check', enabled)
        self.refresh()

    def refresh(self):
        self.timer.stop()
        selections = []
        if self.enabled:
            text = self.editor.toPlainText()
            # Build UTF-16 offsets once, including for text after emoji.
            offsets = [0]
            for char in text:
                offsets.append(offsets[-1] + (2 if ord(char) > 0xffff else 1))
            for start, end, word in prose_words(text, self.highlighter.enabled):
                normalized = self.normalize(word)
                if normalized in self.personal or normalized in self.ignored or self.known(normalized):
                    continue
                selection = QTextEdit.ExtraSelection()
                selection.cursor = QTextCursor(self.editor.document())
                selection.cursor.setPosition(offsets[start])
                selection.cursor.setPosition(offsets[end], QTextCursor.MoveMode.KeepAnchor)
                selection.format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SpellCheckUnderline)
                selection.format.setUnderlineColor(self.color)
                selections.append(selection)
        self.editor.setExtraSelections(selections)

    def accept_word(self, word, permanent=False):
        word = self.normalize(word)
        if permanent:
            self.personal.add(word)
            self.settings.setValue('spelling_words', sorted(self.personal))
        else:
            self.ignored.add(word)
        self.refresh()

    def suggestions(self, word):
        # Bound candidate generation for long identifiers pasted into prose.
        if len(word) > 32:
            return []
        candidates = self.dictionary.candidates(self.normalize(word)) or set()
        ranked = sorted(candidates, key=lambda item: (-self.dictionary.word_frequency[item], item))[:5]
        if word.isupper():
            return [item.upper() for item in ranked]
        if word.istitle():
            return [item.capitalize() for item in ranked]
        return ranked

    def replace(self, cursor, replacement):
        cursor.beginEditBlock()
        cursor.insertText(replacement)
        cursor.endEditBlock()
        self.refresh()

    def context_menu(self, position):
        menu = self.editor.createStandardContextMenu(position)
        self.refresh()  # Resolve the word against current text, even during debounce.
        position = self.editor.cursorForPosition(position).position()
        for selection in self.editor.extraSelections():
            cursor = selection.cursor
            if cursor.selectionStart() <= position < cursor.selectionEnd():
                word = cursor.selectedText()
                first = menu.actions()[0]
                suggestions = self.suggestions(word)
                for suggestion in suggestions:
                    action = menu.addAction(suggestion)
                    action.triggered.connect(lambda checked=False, value=suggestion, c=QTextCursor(cursor): self.replace(c, value))
                    menu.insertAction(first, action)
                if not suggestions:
                    action = menu.addAction('No spelling suggestions')
                    action.setEnabled(False)
                    menu.insertAction(first, action)
                for label, permanent in (('Ignore for this session', False), ('Add to dictionary', True)):
                    action = menu.addAction(label)
                    action.triggered.connect(lambda checked=False, w=word, p=permanent: self.accept_word(w, p))
                    menu.insertAction(first, action)
                menu.insertSeparator(first)
                break
        return menu
