Name:           md-pad
Version:        1.0.4
Release:        1%{?dist}
Summary:        Native Markdown and plain text notepad
# No license has been declared by the project; do not assume an open-source license.
License:        LicenseRef-Not-Specified
URL:            https://github.com/CytheCy/md_pad
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  python3-devel
BuildRequires:  python3-pyside6 >= 6.6
BuildRequires:  python3-pyspellchecker >= 0.8.4
BuildRequires:  desktop-file-utils
Requires:       python3
Requires:       python3-rpm
Requires:       dnf5
Requires:       polkit
Requires:       python3-pyside6 >= 6.6
Requires:       python3-pyspellchecker >= 0.8.4
Requires:       python3-pyspellchecker < 1

%description
MDPad is a native Qt notepad for Markdown and plain text, with source highlighting,
offline English spell checking, a heading panel, and configurable themes.

%prep
%autosetup

%build
# Python sources need no compilation step.

%install
install -d %{buildroot}%{_datadir}/%{name} %{buildroot}%{_bindir}
install -m 644 main.py themes.py spelling.py updater.py update_helper.py VERSION md_pad_icon.svg MDPAD-RPM-KEY.asc %{buildroot}%{_datadir}/%{name}/
install -d %{buildroot}%{_datadir}/%{name}/boxicons
install -m 644 boxicons/*.svg boxicons/LICENSE %{buildroot}%{_datadir}/%{name}/boxicons/
cat > %{buildroot}%{_bindir}/pad <<'EOF'
#!/bin/sh
exec /usr/bin/python3 /usr/share/md-pad/main.py "$@"
EOF
chmod 755 %{buildroot}%{_bindir}/pad
install -Dm644 pad.desktop %{buildroot}%{_datadir}/applications/pad.desktop
install -Dm644 md_pad_icon.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/md-pad.svg

%check
desktop-file-validate %{buildroot}%{_datadir}/applications/pad.desktop
cmp md_pad_icon.svg %{buildroot}%{_datadir}/%{name}/md_pad_icon.svg
cmp md_pad_icon.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/md-pad.svg
QT_QPA_PLATFORM=offscreen %{__python3} - <<'PY'
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtSvg import QSvgRenderer

app = QGuiApplication([])
icon = 'md_pad_icon.svg'
assert QSvgRenderer(icon).isValid(), 'App icon SVG is invalid'
assert not QIcon(icon).pixmap(64, 64).isNull(), 'App icon cannot render'
PY
QT_QPA_PLATFORM=offscreen %{__python3} -m unittest discover -s tests -v

%files
%doc README.md CHANGELOG.md
%{_bindir}/pad
%{_datadir}/%{name}/
%{_datadir}/applications/pad.desktop
%{_datadir}/icons/hicolor/scalable/apps/md-pad.svg

%changelog
* Wed Nov 11 2026 Cy Porter <portercy@gmail.com> - 1.0.4-1
- Publish checksum filenames the installed updater can match.
- Accept checksum filenames from older releases in the updater.

* Wed Nov 11 2026 Cy Porter <portercy@gmail.com> - 1.0.3-1
- Update the app icon and verify it in generated RPMs.
- Improve file dialogs, last-file restoration, themes, and editor behavior.

* Fri Nov 06 2026 Cy Porter <portercy@gmail.com> - 1.0.2-1
- Fix the Fedora release build for the signed updater.

* Fri Nov 06 2026 Cy Porter <portercy@gmail.com> - 1.0.1-1
- Add signed, user-initiated DNF updates.

* Wed Nov 04 2026 Cy Porter <portercy@gmail.com> - 1.0.0-1
- Initial RPM release.
