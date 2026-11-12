"""Run with QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
import subprocess
import sys
import unittest
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor, QPalette, QTextCursor
from PySide6.QtWidgets import QApplication, QRadioButton

from main import MainWindow
from themes import THEMES, TOKENS, TOKEN_DEFAULTS, make_theme, resolve_theme, saved_theme_id


def contrast(a, b):
    def lum(color):
        rgb = QColor(color).getRgbF()[:3]
        linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb]
        return sum(v * w for v, w in zip(linear, (.2126, .7152, .0722)))
    lo, hi = sorted((lum(a), lum(b)))
    return (hi + .05) / (lo + .05)


class ThemeTests(unittest.TestCase):
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
        self.app.processEvents()

    def tearDown(self):
        self.window.editor.document().setModified(False)
        self.window._saved_text = self.window.editor.toPlainText()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_registration_tokens_and_contrast(self):
        self.assertEqual(set(THEMES), {'catppuccin-mocha', 'tokyo-night', 'everforest-dark'})
        required = {'window', 'editor', 'sidebar', 'panel', 'toolbar', 'dialog', 'elevated',
                    'text', 'secondary', 'disabled', 'border', 'accent', 'hover', 'selected',
                    'active_tab', 'inactive_tab', 'selection', 'caret', 'search_match',
                    'search_current', 'focus', 'link', 'success', 'warning', 'error'}
        self.assertTrue(required <= TOKENS)
        self.assertEqual(TOKENS, set(TOKEN_DEFAULTS))
        for theme in THEMES.values():
            self.assertEqual(set(theme.colors), TOKENS)
            self.assertTrue(all(QColor(c).isValid() for c in theme.colors.values()))
            for bg in ('editor', 'panel', 'dialog', 'elevated', 'selection'):
                self.assertGreaterEqual(contrast(theme['text'], theme[bg]), 4.5, (theme.id, bg))
            for token in ('secondary', 'link', 'md_marker', 'md_code', 'md_quote',
                          'md_heading', 'md_heading_secondary', 'md_bracketed'):
                self.assertGreaterEqual(contrast(theme[token], theme['editor']), 4.5, (theme.id, token))
            self.assertGreaterEqual(contrast(theme['focus'], theme['elevated']), 3)

    def test_semantic_token_defaults_and_overrides(self):
        source = THEMES['catppuccin-mocha']
        colors = dict(editor=source['editor'], sidebar=source['sidebar'],
                      deepest=source['window'], elevated=source['elevated'],
                      border=source['border'], text=source['text'],
                      secondary=source['secondary'], muted=source['disabled'],
                      accent=source['accent'], blue=source['link'],
                      green=source['success'], orange=source['md_code'],
                      red=source['error'], yellow=source['warning'],
                      purple=source['md_frontmatter'])
        inherited = make_theme('custom', 'Custom', '', **colors)
        self.assertEqual(set(inherited.colors), TOKENS)
        self.assertEqual(inherited['md_bracketed'], source['md_frontmatter'])
        overridden = make_theme('custom', 'Custom', '', **colors,
                                token_overrides={'md_bracketed': '#FFFFFF'})
        self.assertEqual(overridden['md_bracketed'], '#FFFFFF')
        self.assertEqual(overridden['md_frontmatter'], source['md_frontmatter'])
        with self.assertRaises(ValueError):
            make_theme('custom', 'Custom', '', **colors,
                       token_overrides={'md_braqeted': '#FFFFFF'})

    def test_bracketed_text_uses_its_token(self):
        e = self.window.editor
        e.setPlainText('A [note] and [link](url)\n`[code]`\n- [x] Task')

        def color_at(block_number, offset):
            block = e.document().findBlockByNumber(block_number)
            for item in block.layout().formats():
                if item.start <= offset < item.start + item.length:
                    return item.format.foreground().color().name().upper()
            return None

        for theme in THEMES.values():
            self.window.set_theme(theme.id)
            self.app.processEvents()
            self.assertEqual(color_at(0, 2), theme['md_bracketed'])
            self.assertEqual(color_at(0, 7), theme['md_bracketed'])
            self.assertEqual(color_at(0, 17), theme['md_bracketed'])
            self.assertEqual(color_at(0, 22), theme['md_link'])
            self.assertEqual(color_at(1, 2), theme['md_code'])
            self.assertEqual(color_at(2, 3), theme['md_checkbox'])

    def test_switch_preserves_document_and_typography(self):
        e = self.window.editor
        e.setPlainText('# Chapter One\n\n' + 'A quiet paragraph with **bold**, *italic*, and `code`.\n' * 100)
        e.moveCursor(QTextCursor.MoveOperation.End)
        e.insertPlainText('An ending')
        c = e.textCursor()
        c.setPosition(c.position() - 5, QTextCursor.MoveMode.KeepAnchor)
        e.setTextCursor(c)
        e.verticalScrollBar().setValue(180)
        self.app.processEvents()
        before = (e.toPlainText(), c.position(), c.anchor(), e.document().isModified(),
                  e.document().availableUndoSteps(), e.verticalScrollBar().value(),
                  e.font().toString(), self.window.paragraph_spacing, self.window.max_page_width)
        for identifier in THEMES:
            self.window.set_theme(identifier)
            self.app.processEvents()
            c = e.textCursor()
            after = (e.toPlainText(), c.position(), c.anchor(), e.document().isModified(),
                     e.document().availableUndoSteps(), e.verticalScrollBar().value(),
                     e.font().toString(), self.window.paragraph_spacing, self.window.max_page_width)
            self.assertEqual(before, after)
            self.assertEqual(e.palette().color(QPalette.ColorRole.Base).name().upper(), THEMES[identifier]['editor'])

    def test_selection_persists_and_restores(self):
        dialog = self.window.create_appearance_dialog()
        dialog.show()
        for identifier in THEMES:
            dialog.findChild(QRadioButton, identifier).click()
            self.app.processEvents()
            self.assertEqual(self.window.theme_id, identifier)
            self.assertTrue(dialog.findChild(QRadioButton, identifier).isChecked())
            self.assertEqual(saved_theme_id(QSettings('Pad', 'Pad')), identifier)
            restored = MainWindow()
            self.assertEqual(restored.theme_id, identifier)
            self.assertEqual(restored.theme, THEMES[identifier])
            restored.close()
            restored.deleteLater()
        dialog.close()

    def test_switch_keeps_selected_font_size(self):
        self.window.set_font_size(19)
        for identifier in (*THEMES, 'system', *THEMES):
            with self.subTest(theme=identifier):
                self.window.set_theme(identifier)
                self.app.processEvents()
                self.assertEqual(self.window.font_size, 19)
                self.assertEqual(self.window.editor.font().pointSize(), 19)
                self.assertEqual(self.window.editor.document().defaultFont().pointSize(), 19)
                self.assertEqual(QSettings('Pad', 'Pad').value('font_size', type=int), 19)

        restored = MainWindow()
        self.assertEqual(restored.editor.font().pointSize(), 19)
        restored.close()
        restored.deleteLater()

        self.window.set_font_size(15)
        self.window.set_theme('tokyo-night')
        self.assertEqual(self.window.editor.font().pointSize(), 15)
        self.assertEqual(QSettings('Pad', 'Pad').value('font_size', type=int), 15)

    def test_persistence_in_a_new_process(self):
        script = """
import sys
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from main import MainWindow
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, sys.argv[1])
app = QApplication([])
w = MainWindow()
assert w.theme_id == sys.argv[2], w.theme_id
assert not w.isVisible()
w.close()
"""
        for identifier in THEMES:
            self.window.set_theme(identifier)
            subprocess.run([sys.executable, '-c', script, self.temp.name, identifier],
                           check=True, capture_output=True, text=True)

    def test_switch_preserves_clean_file_and_serialization(self):
        path = Path(self.temp.name) / 'story.md'
        raw = b'\xef\xbb\xbf# Story\r\n\r\nA quiet ending.\r\n'
        path.write_bytes(raw)
        self.assertTrue(self.window.open_file(path))
        for identifier in THEMES:
            self.window.set_theme(identifier)
            self.assertFalse(self.window.editor.document().isModified())
            self.assertEqual(self.window.current_file, path)
            self.assertTrue(self.window.save_file())
            self.assertEqual(path.read_bytes(), raw)

    def test_invalid_saved_id_falls_back_and_system_is_available(self):
        settings = QSettings('Pad', 'Pad')
        settings.setValue('theme', 'missing-theme')
        self.assertEqual(saved_theme_id(settings), 'system')
        self.assertEqual(resolve_theme('missing-theme', self.app.pad_system_palette).id, 'system')
        self.window.set_theme('system')
        self.assertEqual(self.window.theme_id, 'system')

    def test_source_highlighting_and_plain_text_mode(self):
        e = self.window.editor
        source = '# Heading\n## Heading\n### Heading\n#### Heading\n##### Heading\n###### Heading\n> Quote\n- [x] Task\n1. List\n---\n😀 **bold** and *italic* [link](url)\n```\ncode\n```\nOrdinary prose'
        e.setPlainText(source)
        for theme in THEMES.values():
            self.window.set_theme(theme.id)
            self.app.processEvents()
            block = e.document().firstBlock()
            formats = block.layout().formats()
            self.assertEqual(formats[1].format.foreground().color().name().upper(), theme['md_heading'])
            block = e.document().findBlockByNumber(10)
            marker = next(f for f in block.layout().formats() if f.start == 3)
            bold = next(f for f in block.layout().formats() if f.start == 5)
            self.assertEqual(marker.format.foreground().color().alpha(), 0)
            self.assertEqual(bold.length, 4)  # emoji uses two Qt positions
            self.assertEqual(e.document().lastBlock().layout().formats(), [])
            self.assertEqual(e.toPlainText(), source)
        self.window.highlighter.enabled = False
        self.window.highlighter.rehighlight()
        block = e.document().firstBlock()
        while block.isValid():
            self.assertEqual(block.layout().formats(), [])
            block = block.next()


if __name__ == '__main__':
    unittest.main()
