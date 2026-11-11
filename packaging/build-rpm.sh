#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
version="$(cat VERSION)"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
spec_version="$(rpmspec -q --qf '%{version}' packaging/md-pad.spec)"
[[ "$version" == "$spec_version" ]] || { echo 'VERSION and RPM spec disagree' >&2; exit 1; }
if [[ "${GITHUB_REF_TYPE:-}" == tag ]]; then
    [[ "$GITHUB_REF_NAME" == "v$version" ]] || { echo 'Tag and VERSION disagree' >&2; exit 1; }
fi
build_dir="$(mktemp -d)"
trap 'rm -rf "$build_dir"' EXIT
mkdir -p "$build_dir/SOURCES" dist
tar --exclude='__pycache__' --exclude='*.pyc' \
    --transform="s,^,md-pad-$version/," -czf "$build_dir/SOURCES/md-pad-$version.tar.gz" \
    main.py themes.py spelling.py updater.py update_helper.py MDPAD-RPM-KEY.asc VERSION md_pad_icon.svg pad.desktop README.md CHANGELOG.md \
    requirements.txt install.sh boxicons tests packaging
rpmbuild -ba --define "_topdir $build_dir" packaging/md-pad.spec
cp "$build_dir"/RPMS/noarch/*.rpm "$build_dir"/SRPMS/*.rpm dist/
(cd dist && sha256sum *.rpm > SHA256SUMS)
