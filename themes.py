"""Semantic themes shared by Qt widgets and the Markdown source highlighter.

System is retained for existing installations. Explicit themes use Fusion so
platform widget styles cannot silently substitute light control surfaces.
"""
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from PySide6.QtGui import QColor, QPalette


@dataclass(frozen=True)
class Theme:
    id: str
    name: str
    description: str
    colors: Mapping[str, str]

    def __getitem__(self, token: str) -> str:
        return self.colors[token]


def make_theme(identifier, name, description, *, editor, sidebar, deepest,
               elevated, border, text, secondary, muted, accent, blue, green,
               orange, red, yellow, purple, selection=None):
    c = dict(
        window=deepest, editor=editor, sidebar=sidebar, panel=sidebar,
        toolbar=sidebar, dialog=sidebar, elevated=elevated,
        text=text, secondary=secondary, disabled=muted, border=border,
        accent=accent, hover=elevated, selected=selection or elevated,
        active_tab=editor, inactive_tab=sidebar,
        selection=selection or border, selection_text=text, caret=text,
        search_match=elevated, search_current=yellow, search_text=deepest,
        focus=accent, link=blue, success=green, warning=yellow, error=red,
        md_heading=accent, md_heading_secondary=blue, md_bold=text,
        md_italic=text, md_link=blue, md_code=orange, md_code_background=elevated,
        md_quote=secondary, md_marker=secondary, md_list=accent,
        md_checkbox=green, md_rule=secondary, md_frontmatter=purple,
    )
    return Theme(identifier, name, description, MappingProxyType(c))


THEMES = {t.id: t for t in (
    make_theme('catppuccin-mocha', 'Catppuccin Mocha', 'Soft lavender · calm and elegant',
        editor='#1E1E2E', sidebar='#181825', deepest='#11111B', elevated='#313244',
        border='#45475A', text='#CDD6F4', secondary='#A6ADC8', muted='#7F849C',
        accent='#CBA6F7', blue='#89B4FA', green='#A6E3A1', orange='#FAB387',
        red='#F38BA8', yellow='#F9E2AF', purple='#CBA6F7'),
    make_theme('tokyo-night', 'Tokyo Night', 'Midnight blue · crisp and focused',
        editor='#1A1B26', sidebar='#16161E', deepest='#16161E', elevated='#24283B',
        border='#414868', text='#C0CAF5', secondary='#A9B1D6', muted='#787C99',
        accent='#7AA2F7', blue='#7DCFFF', green='#9ECE6A', orange='#FF9E64',
        red='#F7768E', yellow='#E0AF68', purple='#BB9AF7'),
    make_theme('everforest-dark', 'Everforest Dark', 'Warm forest · a literary atmosphere',
        editor='#2D353B', sidebar='#232A2E', deepest='#232A2E', elevated='#343F44',
        border='#475258', text='#D3C6AA', secondary='#9DA9A0', muted='#859289',
        accent='#A7C080', blue='#7FBBB3', green='#83C092', orange='#E69875',
        red='#E67E80', yellow='#DBBC7F', purple='#D699B6', selection='#3D484D'),
)}
TOKENS = frozenset(next(iter(THEMES.values())).colors)
DEFAULT_THEME = 'system'


def resolve_theme(identifier, system_palette):
    if identifier in THEMES:
        return THEMES[identifier]
    dark = system_palette.color(QPalette.ColorRole.Window).lightness() < 128
    return make_theme('system', 'System', 'Follow the desktop appearance at launch',
        editor='#171A20' if dark else '#FFFFFF', sidebar='#20242C' if dark else '#F5F6F8',
        deepest='#171A20' if dark else '#FFFFFF', elevated='#303744' if dark else '#E8ECF2',
        border='#343B46' if dark else '#CFD5DF', text='#E9EDF4' if dark else '#252C37',
        secondary='#A9B7C9' if dark else '#586579', muted='#8993A3' if dark else '#69798E',
        accent='#8FB8FF' if dark else '#436AAB', blue='#8FB8FF' if dark else '#436AAB',
        green='#A6E3A1' if dark else '#376B36', orange='#D9B98C' if dark else '#93632F',
        red='#F38BA8' if dark else '#AC283D', yellow='#F9E2AF' if dark else '#765B16',
        purple='#CBA6F7' if dark else '#72509A')


def saved_theme_id(settings):
    identifier = settings.value('theme', DEFAULT_THEME, type=str)
    return identifier if identifier in THEMES or identifier == DEFAULT_THEME else DEFAULT_THEME


def palette(theme):
    p = QPalette()
    roles = dict(Window='window', WindowText='text', Base='editor', AlternateBase='elevated',
                 ToolTipBase='elevated', ToolTipText='text', Text='text', Button='elevated',
                 ButtonText='text', BrightText='text', Highlight='selection',
                 HighlightedText='selection_text', Link='link', LinkVisited='link',
                 PlaceholderText='secondary', Light='border', Midlight='elevated',
                 Dark='sidebar', Mid='border', Shadow='window', Accent='accent')
    for role, token in roles.items():
        p.setColor(getattr(QPalette.ColorRole, role), QColor(theme[token]))
    for role in ('Text', 'WindowText', 'ButtonText', 'PlaceholderText'):
        p.setColor(QPalette.ColorGroup.Disabled, getattr(QPalette.ColorRole, role), QColor(theme['disabled']))
    return p


def stylesheet(t):
    return f'''
        QWidget {{ color: {t['text']}; }}
        QMainWindow {{ background: {t['window']}; }}
        QDialog, QMessageBox {{ background: {t['dialog']}; }}
        QTextEdit, QPlainTextEdit, QLineEdit, QSpinBox, QComboBox, QAbstractItemView {{
            background: {t['editor']}; color: {t['text']};
            selection-background-color: {t['selection']}; selection-color: {t['selection_text']}; }}
        #editor {{ border: none; }}
        #headingPanel {{ background: {t['sidebar']}; }}
        QSplitter#contentSplitter::handle {{ background: {t['border']}; }}
        QSplitter#contentSplitter::handle:hover {{ background: {t['accent']}; }}
        #headingList {{ background: {t['sidebar']}; border: none; }}
        #headingList::item {{ padding: 7px 4px; }}
        #headingList::item:hover {{ background: {t['hover']}; }}
        #findFooter, #replaceFooter {{ background: {t['toolbar']}; border-top: 1px solid {t['border']}; }}
        #findCount, #replaceCount {{ color: {t['secondary']}; }}
        #status, QMenuBar, QToolBar {{ background: {t['toolbar']}; }}
        #status {{ border-top: 1px solid {t['border']}; }}
        #status QLabel {{ color: {t['secondary']}; font-size: 11px; }}
        #title {{ font-size: 15px; font-weight: 600; }}
        QMenuBar {{ border-bottom: 1px solid {t['border']}; padding: 3px 6px; }}
        QMenuBar::item {{ padding: 7px 11px; border-radius: 5px; }}
        QMenuBar::item:selected, QMenu::item:selected {{ background: {t['hover']}; }}
        QMenu {{ background: {t['panel']}; border: 1px solid {t['border']}; padding: 5px; }}
        QMenu::item {{ padding: 6px 24px; }}
        QMenu::separator {{ height: 1px; background: {t['border']}; margin: 5px 8px; }}
        QPushButton, QToolButton {{ background: {t['elevated']}; border: 1px solid {t['border']};
            border-radius: 5px; padding: 7px 12px; }}
        #replaceFooter QToolButton {{ padding: 5px 6px; }}
        QPushButton:hover, QToolButton:hover {{ background: {t['hover']}; border-color: {t['accent']}; }}
        QPushButton:pressed, QToolButton:pressed, QPushButton:checked {{ background: {t['selected']}; }}
        #findFooter QToolButton:checked, #replaceFooter QToolButton:checked {{
            background: {t['accent']}; color: {t['window']}; border-color: {t['accent']}; }}
        QPushButton:focus, QToolButton:focus, QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
            border: 1px solid {t['focus']}; }}
        QRadioButton:focus, QCheckBox:focus {{ outline: 1px solid {t['focus']}; }}
        QLineEdit, QSpinBox, QComboBox {{ border: 1px solid {t['border']}; border-radius: 4px; padding: 5px; }}
        QLineEdit QToolButton {{ background: transparent; border: none; padding: 0; }}
        QWidget:disabled, QMenu::item:disabled {{ color: {t['disabled']}; }}
        QToolButton#windowControl, QToolButton#closeControl {{ background: transparent; border: none;
            border-radius: 0; padding: 0; min-width: 42px; min-height: 30px; }}
        QToolButton#windowControl:hover {{ background: {t['hover']}; }}
        QToolButton#windowControl:checked {{ background: {t['selected']}; }}
        QToolButton#closeControl:hover {{ background: {t['error']}; color: {t['window']}; }}
        QToolTip {{ background: {t['elevated']}; color: {t['text']}; border: 1px solid {t['border']}; padding: 5px; }}
        QScrollBar:vertical {{ background: {t['editor']}; width: 12px; margin: 0; }}
        QScrollBar:horizontal {{ background: {t['editor']}; height: 12px; margin: 0; }}
        QScrollBar::handle {{ background: {t['border']}; border-radius: 5px; min-height: 28px; min-width: 28px; }}
        QScrollBar::handle:hover {{ background: {t['secondary']}; }}
        QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
        QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
        QTabBar::tab {{ background: {t['inactive_tab']}; padding: 7px; }}
        QTabBar::tab:selected {{ background: {t['active_tab']}; border-bottom: 2px solid {t['accent']}; }}
    '''


def apply_application_theme(app, theme):
    app.setPalette(palette(theme))
    app.setStyleSheet(stylesheet(theme))
