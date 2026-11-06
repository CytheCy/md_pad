# MDPad

A small native notepad for Markdown and plain text, designed for Fedora KDE.

## Install on Fedora KDE

Download the `.noarch.rpm` from the [latest release](https://github.com/CytheCy/md_pad/releases/latest), then install it on Fedora 44:

```bash
sudo dnf install ./md-pad-1.0.0-1.fc44.noarch.rpm
```

DNF installs the required dependencies. Launch **MDPad** from the application menu
or run `pad [note.md]`. Check the version with `pad --version`.
Remove the RPM with `sudo dnf remove md-pad`.

If you previously used `install.sh`, its per-user launcher and desktop entry
take precedence over the RPM. Remove those generated files when switching:

```bash
rm -f ~/.local/bin/pad ~/.local/share/applications/pad.desktop
```

### Install from source

```bash
bash install.sh
```

The installer creates a local virtual environment and adds MDPad to the KDE application menu. It also registers it as an option for `.md` and `.txt` files. To run directly from this checkout instead:

```bash
python3 main.py [note.md]
```

Use **File → Open…** to open a note, or drag a file onto the editor. Markdown source stays directly editable while headings, emphasis, code, links, lists, and quotes receive visual styling. Heading `#` markers stay hidden until you click or move the cursor onto that line, and hide again when you leave it.

Click a Markdown link's label or a web address in the text to open it in your system's default browser. Drag to select text, or hold Shift while clicking to place the cursor without opening the link. Addresses inside code spans and fenced code blocks stay as editable code.

Start a bullet with `- `, `* `, or `+ ` at the beginning of a line. Inactive bullet lines show an indented dot; the Markdown marker reappears when you move the cursor onto the line. Enter continues the bullet with the same marker; Enter again on an empty bullet ends the list and leaves only one newline in the saved text.

Numbered lists work the same way with markers such as `1. ` or `1) `. Inactive items show an indented number, and Enter continues with the next number. Enter on the empty next item ends the list without adding a blank line to the saved text.

Wrap text in `*single*` or `_single_` markers for italics, and `**double**` or `__double__` markers for bold. The markers hide while the cursor is on another line and reappear for editing when you move onto their line; the saved Markdown retains them.

Single backticks wrap inline code, and triple backticks on separate lines fence a code block. Fenced code appears in a rounded, padded panel. Hover over the panel to reveal the copy icon at the upper right; clicking it copies the code without the fence lines. Inline backticks reappear when you move the cursor onto their line, and both code fences reappear when the cursor is anywhere inside their block. The saved Markdown retains all delimiters.

Type `---` on its own line for a horizontal rule. It appears as a line until you move the cursor onto it, when the editable Markdown source reappears. `***` and `___` work too.

Tables with a header and a `---` delimiter row display as aligned cells with borders. Alignment markers such as `:---`, `:---:`, and `---:` control each column. Click a row to edit its Markdown source; the table view returns when you leave the row. Pipes escaped with `\|` or inside inline code stay in their cell. Tab and Shift+Tab move between cells; Tab from the last cell adds a row when needed. Enter at the end of a data row also adds a row. Empty and uneven rows remain editable, and the saved text keeps its original Markdown.

Use **File → Open Recent** to reopen one of your last 10 opened or saved files. The list is remembered across restarts; **Clear Recent** clears it.

Markdown notes with two or more `#` headings show a heading panel on the right. Click the side panel icon immediately left of Minimize to cycle through **Narrow**, **Full**, and **Closed**. Narrow shows the first three characters of each heading; Full shows more of each heading and lets you drag the divider to adjust its width. Choose a state directly from **Settings → Heading panel**. The state and Full width are remembered across restarts. Click a heading to jump to it in the editor. The icon appears only when there are at least two headings. The list updates as you edit and excludes fenced code. Plain text files do not show the panel.

Spell checking is enabled by default and works offline with an English dictionary.
Misspelled words receive a wavy underline; right-click one for suggestions,
**Ignore for this session**, or **Add to dictionary**. Added words are remembered
across restarts. Corrections can be undone with Ctrl+Z. Markdown code, link
destinations, URLs, and email addresses are skipped. Toggle checking with
**Settings → Spell check (English)**; this preference is also remembered.
Existing installations should rerun `bash install.sh` to install the new dependency.

Use **File → Remove Extra ↵** to collapse consecutive line breaks into a single line break throughout the note. Undo restores the removed breaks in one step.

Use **File → Remove Extra Spaces** to collapse repeated spaces into one and remove spaces immediately before or after a newline throughout the note. Line breaks and tabs are preserved. Undo restores the removed spaces in one step.

Each newline displays as a paragraph break with extra space after it. Adjust the gap in **Settings → Paragraph spacing…**. This changes the display only; saved files keep their original newlines.

Use **Settings → Font size…** to choose a text size from 6 to 72 points. **Ctrl++** (or **Ctrl+=**) increases the size by one point; **Ctrl+-** decreases it. Markdown headings scale with the text. Font size, paragraph spacing, and page width are remembered across restarts.

Use **Settings → Max Page Width…** to limit the text page width in pixels (950 px by default). Wider windows add margins on both sides to keep the page centered; narrower windows wrap the text to fit. The setting is remembered across restarts. Set it to **Unlimited** (0) to use the full available width.

Use `Ctrl+N` for a new note, `Ctrl+O` to open a file, `Ctrl+S` to save, and `Ctrl+Shift+S` to save as. Unsaved changes are confirmed before closing or changing files.

## Appearance

Choose **Settings → Themes…** for **Catppuccin Mocha**, **Tokyo Night**,
or **Everforest Dark**. Each option has a miniature color preview and a radio
indicator. Changes apply immediately and save automatically. **System** retains
the previous light/dark appearance based on desktop colors at launch and remains
the default for existing installations.

Themes preserve the document, undo history, cursor, selection, scrolling, and
all typography preferences. Saved colors are applied before the main window is
shown. Qt widget file dialogs are used so open/save dialogs share the palette;
OS-owned window decorations and file-type icons remain platform controlled.

`themes.py` owns stable identifiers, immutable semantic color maps, the Qt
palette, and application stylesheets. `main.py` uses the same tokens for source
Markdown highlighting and the theme selector. Ordinary prose stays in the body
color; headings, lists, quotes, code, and links receive restrained accents. The
editor remains a source editor: there is no rendered preview, search UI,
tab system, or YAML-specific highlighter. Tokens for these roles are available
without adding those features.

## Validation

Install `requirements.txt` first; no additional test dependencies are needed:

```bash
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
python3 -m py_compile main.py themes.py spelling.py
```

Tests cover token completeness, text contrast, live selection, persistence in a
new process, fallback behavior, source highlighting (including Unicode offsets),
plain text mode, document/undo/selection/scroll preservation, typography, and
BOM/line-ending preservation when saving. Offscreen screenshots of the three
themes and their dialogs are in `artifacts/`. A real KDE session is still needed
to assess compositor decorations and native desktop interaction.

## Building and releasing an RPM

GitHub Actions builds and tests an RPM on pushes to `main`, pull requests, and
manual runs. Pushing a `v*` tag also publishes a GitHub release with the binary
RPM, source RPM, and SHA-256 checksums. The tag must match `VERSION` and the
version in `packaging/md-pad.spec`. No additional GitHub secrets are needed.

To build and test locally with Podman:

```bash
podman run --rm -v "$PWD:/src:Z" -w /src \
  registry.fedoraproject.org/fedora:44 bash packaging/ci.sh
```

Output is written to `dist/`. For a future release, update `VERSION`, the spec
version/changelog, and `CHANGELOG.md`, commit, then push the commit and its tag:

```bash
git tag -a v1.0.1 -m "MDPad v1.0.1"
git push --atomic origin main v1.0.1
```

The project has not declared a license; RPM metadata records this as
`LicenseRef-Not-Specified` without granting additional rights.
