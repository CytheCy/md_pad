# MDPad v1.0.6

- Remember the window's exact size, position, and maximized state, including placement against screen edges. Use XWayland when available to restore positions on Wayland desktops.
- Fix trackpad scrolling while a Markdown line is active.
- Keep unsaved-change detection accurate when display formatting changes Qt's modified flag.

# MDPad v1.0.5

- Continue the in-app upgrade after the administrator approves the release key.

# MDPad v1.0.4

- Fix the release checksum list so installed MDPad versions can verify and install updates.
- Accept checksum lists from older releases when checking future updates.

# MDPad v1.0.3

- Use the redesigned app icon in the window, desktop launcher, and RPM installer.
- Restore the last open file and use the native KDE file picker.
- Improve heading navigation, themes, tables, font sizing, and editor controls.

# MDPad v1.0.2

- Fix the Fedora release build for the signed updater.

# MDPad v1.0.1

- Add a signed, user-initiated RPM updater under Settings → Updates.
- Keep RPM package identity and existing user settings and data unchanged.

# MDPad v1.0.0

First release of MDPad, a native Markdown and plain text notepad for Fedora KDE.

- Editable Markdown source with syntax styling and a heading navigation panel.
- Offline English spell checking, suggestions, and a personal dictionary.
- Three built-in themes plus system colors.
- Configurable font size, paragraph spacing, and page width.
- Recent files, drag-and-drop opening, and whitespace cleanup actions.
- Fedora RPM installer with an application menu entry and file associations.

Download the `.noarch.rpm` asset and install it with
`sudo dnf install ./md-pad-1.0.0-1.fc44.noarch.rpm`.
DNF installs the required Qt/Python libraries and spelling dictionary.
The `.src.rpm` asset is for rebuilding the package, not installing the app.
