#!/usr/bin/env bash
# Run inside a disposable Fedora container as root.
set -euo pipefail
dnf install -y rpm-build python3-devel python3-pyside6 python3-pyspellchecker \
    desktop-file-utils tar gzip
bash packaging/build-rpm.sh
dnf install -y dist/*.noarch.rpm
test "$(pad --version)" = "Pad $(cat VERSION)"
cd /tmp
QT_QPA_PLATFORM=offscreen python3 - <<'PY'
import sys
sys.path.insert(0, '/usr/share/md-pad')
from PySide6.QtWidgets import QApplication
from main import MainWindow
app = QApplication([])
window = MainWindow()
window.show()
app.processEvents()
window.close()
print('Installed RPM window smoke test passed')
PY
rpm -V md-pad
