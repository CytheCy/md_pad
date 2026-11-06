#!/usr/bin/env bash
# Run in Fedora with rpm-sign and gnupg2; MDPAD_SIGNING_KEY is an armored secret key.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${MDPAD_SIGNING_KEY:?Set the MDPAD_SIGNING_KEY repository secret to the armored private key}"
sign_home="$(mktemp -d)"
trap 'rm -rf "$sign_home"' EXIT
chmod 700 "$sign_home"
export GNUPGHOME="$sign_home"
printf '%s\n' "$MDPAD_SIGNING_KEY" | gpg --batch --import >/dev/null 2>&1
expected="$(gpg --show-keys --with-colons MDPAD-RPM-KEY.asc | awk -F: '$1 == "fpr" {print $10; exit}')"
actual="$(gpg --list-secret-keys --with-colons | awk -F: '$1 == "fpr" {print $10; exit}')"
[[ -n "$expected" && "$expected" == "$actual" ]] || { echo 'Signing key does not match bundled public key' >&2; exit 1; }
for package in dist/*.rpm; do
    rpmsign --define "_gpg_name $expected" --addsign "$package"
done
rpmdb="$(mktemp -d)"
trap 'rm -rf "$sign_home" "$rpmdb"' EXIT
rpm --dbpath "$rpmdb" --initdb
rpmkeys --dbpath "$rpmdb" --import MDPAD-RPM-KEY.asc
for package in dist/*.rpm; do
    rpmkeys --dbpath "$rpmdb" --checksig "$package"
done
(cd dist && sha256sum ./*.rpm > SHA256SUMS)
