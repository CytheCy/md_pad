#!/usr/bin/env bash
# Fedora container integration test: upgrade the tagged 1.0.0 RPM in place.
set -euo pipefail
cd "$(dirname "$0")/.."
old_tree="$(mktemp -d)"
test_home="$(mktemp -d)"
trap 'rm -rf "$old_tree" "$test_home"' EXIT
git -c safe.directory="$(pwd)" archive v1.0.0 | tar -x -C "$old_tree"
(cd "$old_tree" && env -u GITHUB_REF_TYPE -u GITHUB_REF_NAME bash packaging/build-rpm.sh)
dnf5 install -y "$old_tree"/dist/md-pad-1.0.0-*.noarch.rpm
export XDG_CONFIG_HOME="$test_home/config"
export XDG_DATA_HOME="$test_home/data"
export XDG_STATE_HOME="$test_home/state"
mkdir -p "$XDG_DATA_HOME/MDPad" "$XDG_STATE_HOME/MDPad"
printf 'database fixture\n' > "$XDG_DATA_HOME/MDPad/notes.db"
printf 'state fixture\n' > "$XDG_STATE_HOME/MDPad/session"
printf '# Saved note\n' > "$test_home/note.md"
python3 - <<'PY'
from PySide6.QtCore import QSettings
s = QSettings('Pad', 'Pad')
s.setValue('theme', 'tokyo-night')
s.setValue('recent_files', ['note.md'])
s.setValue('font_size', 18)
s.sync()
assert s.status() == QSettings.Status.NoError
PY
before="$(sha256sum "$XDG_CONFIG_HOME/Pad/Pad.conf" "$XDG_DATA_HOME/MDPad/notes.db" "$XDG_STATE_HOME/MDPad/session" "$test_home/note.md")"
dnf5 upgrade -y dist/md-pad-"$(cat VERSION)"-*.noarch.rpm
test "$(pad --version)" = "MDPad $(cat VERSION)"
test "$(rpm -q --qf '%{VERSION}' md-pad)" = "$(cat VERSION)"
test "$before" = "$(sha256sum "$XDG_CONFIG_HOME/Pad/Pad.conf" "$XDG_DATA_HOME/MDPad/notes.db" "$XDG_STATE_HOME/MDPad/session" "$test_home/note.md")"
QT_QPA_PLATFORM=offscreen python3 - <<'PY'
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
import sys
sys.path.insert(0, '/usr/share/md-pad')
from main import MainWindow
app = QApplication([])
window = MainWindow()
assert window.theme_id == 'tokyo-night'
assert window.font_size == 18
assert QSettings('Pad', 'Pad').value('recent_files', [], type=list) == ['note.md']
window.show()
app.processEvents()
window.close()
PY
rpm -V md-pad
