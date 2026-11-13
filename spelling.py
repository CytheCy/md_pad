"""Offline English spelling with display-only underlines and undoable corrections."""
import re
from collections import OrderedDict
from time import perf_counter

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


class SpellingBlock:
    def __init__(self, block, markdown, before, after, inline_before, inline_after, selections):
        self.block = block
        self.markdown = markdown
        self.before = before
        self.after = after
        self.inline_before = inline_before
        self.inline_after = inline_after
        self.text = block.text()
        self.selections = selections


class Spelling(QObject):
    BATCH_SECONDS = 0.004
    BATCH_STEPS = 128
    CACHE_SIZE = 8192

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
        self._known_cache = OrderedDict()
        self._marked = {}
        self._pending_start = self._pending_end = None
        self._job = None
        self._markdown = None
        self._published_color = None
        self._publish_needed = False
        self._last_publish = 0
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.refresh)
        self.batch_timer = QTimer(self)
        self.batch_timer.setSingleShot(True)
        self.batch_timer.setInterval(5)
        self.batch_timer.timeout.connect(self.process_batch)
        editor.sourceEdited.connect(self.schedule)
        editor.documentAboutToChange.connect(self.reset_document_state)

    @staticmethod
    def normalize(word):
        return word.replace('’', "'").lower()

    def known(self, word):
        if word in self._known_cache:
            self._known_cache.move_to_end(word)
            return self._known_cache[word]
        result = not self.dictionary.unknown([word])
        self._known_cache[word] = result
        if len(self._known_cache) > self.CACHE_SIZE:
            self._known_cache.popitem(last=False)
        return result

    def cancel_batch(self):
        self.batch_timer.stop()
        if self._job is not None:
            if (self._pending_start is not None and self._pending_end is not None
                    and self._pending_start.position() > self._pending_end.position()):
                self._pending_end = QTextCursor(self._pending_start)
                self._pending_end.movePosition(QTextCursor.MoveOperation.EndOfBlock)
            self._job.close()
            self._job = None

    def schedule(self, position, removed, added):
        if self.enabled:
            # A suspended paragraph is uncommitted; keep its live cursor range
            # and discard partial results before merging the new edit.
            self.cancel_batch()
            document = self.editor.document()
            first = document.findBlock(position)
            if not first.isValid():
                # setPlainText briefly removes all blocks before inserting the
                # replacement document. Do not retain a null range cursor.
                self._pending_start = self._pending_end = None
                self._marked.clear()
                self._publish_needed = True
                self.timer.start()
                return
            start = QTextCursor(first)
            last = document.findBlock(min(position + added, document.characterCount() - 1))
            cached = self.editor.block_data(first).spelling
            # Cross-line inline-code delimiters can change exclusions before
            # the edited line. Revisit that dependency in batches as well.
            if self.highlighter.enabled and (
                    (added > 1 and last != first) or '`' in first.text() or (cached is not None and (
                        '`' in cached.text or (cached.inline_before is not None
                                              and not cached.inline_before[1].isValid())))):
                start = QTextCursor(document)
            end = QTextCursor(last)
            end.movePosition(QTextCursor.MoveOperation.EndOfBlock)
            if self._pending_start is None or self._pending_start.isNull() or start.position() < self._pending_start.position():
                self._pending_start = start
            if self._pending_end is None or self._pending_end.isNull() or end.position() > self._pending_end.position():
                self._pending_end = end
            self._publish_needed |= bool(removed)
            self.timer.start()

    def request_full_check(self):
        self.cancel_batch()
        self._pending_start = QTextCursor(self.editor.document())
        self._pending_end = QTextCursor(self.editor.document())
        self._pending_end.movePosition(QTextCursor.MoveOperation.End)
        self._marked.clear()
        self._publish_needed = True

    def reset_document_state(self):
        """Drop pending work and paragraph references before replacing a note."""
        self.timer.stop()
        self.cancel_batch()
        self._pending_start = self._pending_end = None
        self._marked.clear()
        self._markdown = None
        self._publish_needed = True

    def set_enabled(self, enabled):
        self.enabled = enabled
        self.settings.setValue('spell_check', enabled)
        self._markdown = None
        if not enabled:
            self.cancel_batch()
            self._pending_start = self._pending_end = None
            self._marked.clear()
            self._publish_needed = True
        self.refresh()

    def refresh(self):
        """Start/resume a bounded check; large notes complete across event turns."""
        self.timer.stop()
        if self.enabled and self._markdown != self.highlighter.enabled:
            self._markdown = self.highlighter.enabled
            self.request_full_check()
        if self._published_color != self.color.name():
            self.cancel_batch()
            for record in self._marked.values():
                for selection in record.selections:
                    selection.format.setUnderlineColor(self.color)
            self._published_color = self.color.name()
            self._publish_needed = True
        self.process_batch()

    def inline_end(self, block, length):
        current = block.next()
        while current.isValid():
            match = re.search(r'`+', current.text())
            if match:
                return (block, current, match.start() + length) if len(match[0]) >= length else None
            current = current.next()
            yield
        return None

    def check_block(self, block, fence, inline=None):
        """Yield between words, including within a very long paragraph."""
        text = block.text()
        start = 0
        if inline is not None and inline[1] == block:
            start = inline[2]
            inline = None
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})', text) if self._markdown else None
        if fence:
            if (marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence)
                    and not text[marker.end():].strip()):
                fence = None
            yield
            return fence, inline, []
        if marker:
            yield
            return marker[1], inline, []
        if inline is not None:
            yield
            return None, inline, []
        end = len(text)
        if self._markdown:
            segment = text[start:]
            last = re.search(r'(`+)[^`]*$', segment)
            if last and not any(match.start() <= last.start() < match.end()
                                for match in re.finditer(r'(`+)[^`]*?\1', segment)):
                inline = yield from self.inline_end(block, len(last[1]))
                if inline is not None:
                    end = start + last.start()
        selections = []
        segment = text[start:end]
        python_offset = 0
        qt_offset = len(text[:start].encode('utf-16-le')) // 2
        for start, end, word in prose_words(segment, self._markdown):
            normalized = self.normalize(word)
            if normalized not in self.personal and normalized not in self.ignored and not self.known(normalized):
                # Convert only the relevant spans, never the whole document.
                qt_offset += len(segment[python_offset:start].encode('utf-16-le')) // 2
                length = len(segment[start:end].encode('utf-16-le')) // 2
                python_offset = end
                selection = QTextEdit.ExtraSelection()
                selection.cursor = QTextCursor(block)
                selection.cursor.setPosition(block.position() + qt_offset)
                selection.cursor.setPosition(block.position() + qt_offset + length, QTextCursor.MoveMode.KeepAnchor)
                selection.format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SpellCheckUnderline)
                selection.format.setUnderlineColor(self.color)
                selections.append(selection)
                qt_offset += length
            yield
        return None, inline, selections

    def scan_pending(self):
        block = self._pending_start.block()
        previous = block.previous()
        cached = self.editor.block_data(previous).spelling if previous.isValid() else None
        if previous.isValid() and (cached is None or cached.markdown != self._markdown):
            block = self.editor.document().firstBlock()
            self._pending_start = QTextCursor(block)
            cached = None
        fence = cached.after if cached is not None else None
        inline = cached.inline_after if cached is not None else None
        while block.isValid():
            cache = self.editor.block_data(block)
            old = cache.spelling
            if (block.position() > self._pending_end.position() and old is not None
                    and old.markdown == self._markdown and old.before == fence and old.inline_before == inline):
                break
            before = fence
            inline_before = inline
            fence, inline, selections = yield from self.check_block(block, fence, inline)
            record = SpellingBlock(block, self._markdown, before, fence, inline_before, inline, selections)
            if old is not None:
                self._marked.pop(id(old), None)
            cache.spelling = record
            if selections:
                self._marked[id(record)] = record
            if selections or (old is not None and old.selections):
                self._publish_needed = True
            block = block.next()
            if block.isValid():
                self._pending_start = QTextCursor(block)
            yield
        self._pending_start = self._pending_end = None

    def process_batch(self):
        self.batch_timer.stop()
        if self.enabled and self._pending_start is not None:
            if self._job is None:
                self._job = self.scan_pending()
            deadline = perf_counter() + self.BATCH_SECONDS
            for _ in range(self.BATCH_STEPS):
                try:
                    next(self._job)
                except StopIteration:
                    self._job = None
                    break
                if perf_counter() >= deadline:
                    break
        if self._job is not None and self.enabled:
            self.batch_timer.start()
        # Publish at most once per frame while a large scan is in progress.
        if self._publish_needed and (self._job is None or perf_counter() - self._last_publish >= 0.016):
            selections = []
            for key, record in list(self._marked.items()):
                if (not record.block.isValid()
                        or self.editor.block_data(record.block).spelling is not record):
                    del self._marked[key]
                else:
                    selections.extend(record.selections)
            selections.sort(key=lambda selection: selection.cursor.selectionStart())
            self.editor.setExtraSelections(selections)
            self._publish_needed = False
            self._last_publish = perf_counter()

    def accept_word(self, word, permanent=False):
        word = self.normalize(word)
        if permanent:
            self.personal.add(word)
            self.settings.setValue('spelling_words', sorted(self.personal))
        else:
            self.ignored.add(word)
        self.cancel_batch()
        for key, record in list(self._marked.items()):
            record.selections = [selection for selection in record.selections
                                 if self.normalize(selection.cursor.selectedText()) != word]
            if not record.selections:
                del self._marked[key]
        self._publish_needed = True
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
        # Resolve only the clicked paragraph, even if a large initial check has
        # not reached it yet. Opening a menu must not drain the background queue.
        clicked = self.editor.cursorForPosition(position)
        block = clicked.block()
        cache = self.editor.block_data(block).spelling
        cache_current = self._pending_start is None or self._pending_start.position() > block.position()
        in_code = (cache.before is not None if cache_current and cache is not None and cache.markdown
                   else block.userState() == 1 or block.previous().userState() == 1)
        if cache_current and cache is not None and cache.markdown:
            if cache.inline_before is not None:
                _, closing, end = cache.inline_before
                in_code |= (closing != block or clicked.positionInBlock() <
                            len(block.text()[:end].encode('utf-16-le')) // 2)
            if cache.inline_after is not None and cache.inline_after[0] == block:
                opening = block.text().rfind('`')
                in_code |= clicked.positionInBlock() >= len(block.text()[:opening].encode('utf-16-le')) // 2
        if self.enabled and not (self.highlighter.enabled and in_code):
            text = block.text()
            offset = clicked.positionInBlock()
            for start, end, word in prose_words(text, self.highlighter.enabled):
                qt_start = len(text[:start].encode('utf-16-le')) // 2
                qt_end = qt_start + len(text[start:end].encode('utf-16-le')) // 2
                if not qt_start <= offset <= qt_end:
                    continue
                normalized = self.normalize(word)
                if normalized in self.personal or normalized in self.ignored or self.known(normalized):
                    break
                cursor = QTextCursor(block)
                cursor.setPosition(block.position() + qt_start)
                cursor.setPosition(block.position() + qt_end, QTextCursor.MoveMode.KeepAnchor)
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
