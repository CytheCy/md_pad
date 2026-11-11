#!/usr/bin/env bash
# Run inside a disposable Fedora container as root.
set -euo pipefail
dnf install -y rpm-build python3-devel python3-pyside6 python3-pyspellchecker python3-rpm git \
    desktop-file-utils tar gzip
bash packaging/build-rpm.sh
python3 - <<'PY'
from pathlib import Path
from updater import release_checksum

checksums = Path('dist/SHA256SUMS').read_text()
for rpm in Path('dist').glob('*.rpm'):
    name = rpm.name
    assert f'  {name}\n' in checksums, f'Checksum entry must use a bare filename: {name}'
    release_checksum(checksums, name)
PY
(cd dist && sha256sum -c SHA256SUMS)
bash packaging/test-upgrade.sh
test "$(pad --version)" = "MDPad $(cat VERSION)"
cmp md_pad_icon.svg /usr/share/md-pad/md_pad_icon.svg
cmp md_pad_icon.svg /usr/share/icons/hicolor/scalable/apps/md-pad.svg
cd /tmp
QT_QPA_PLATFORM=offscreen python3 - <<'PY'
import sys
sys.path.insert(0, '/usr/share/md-pad')
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from main import MainWindow
app = QApplication([])
app.setWindowIcon(QIcon('/usr/share/md-pad/md_pad_icon.svg'))
assert not app.windowIcon().pixmap(64, 64).isNull(), 'Installed window icon cannot render'
window = MainWindow()
window.show()
app.processEvents()
window.close()
print('Installed RPM window smoke test passed')
PY
rpm -V md-pad
