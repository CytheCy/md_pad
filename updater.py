"""User initiated, signed RPM updates for the Fedora build."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLabel, QPushButton,
                               QProgressBar, QTextEdit, QVBoxLayout)

API = "https://api.github.com/repos/CytheCy/md_pad/releases/latest"
PACKAGE = "md-pad"
KEY = Path(__file__).with_name("MDPAD-RPM-KEY.asc")
MAX_RPM = 100 * 1024 * 1024


class UpdateError(Exception):
    pass


def run(*args: str) -> str:
    result = subprocess.run(args, text=True, capture_output=True, timeout=30, check=False)
    if result.returncode:
        raise UpdateError((result.stderr or result.stdout).strip() or f"{args[0]} failed")
    return result.stdout.strip()


def rpm_version_compare(a: tuple[str, str, str], b: tuple[str, str, str]) -> int:
    # Fedora's python3-rpm implements the same EVR ordering as the transaction engine.
    import rpm
    return rpm.labelCompare(a, b)


def installed_evr() -> tuple[str, str, str]:
    value = run("rpm", "-q", "--qf", "%{EPOCHNUM}\n%{VERSION}\n%{RELEASE}\n", PACKAGE)
    parts = value.splitlines()
    if len(parts) != 3:
        raise UpdateError("Could not read the installed RPM version.")
    return tuple(parts)  # type: ignore[return-value]


def fetch(url: str, *, limit: int = 2_000_000) -> bytes:
    if not url.startswith("https://"):
        raise UpdateError("Release URL is not HTTPS.")
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                                   "User-Agent": "MDPad-updater"})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            if not response.geturl().startswith("https://"):
                raise UpdateError("Release redirected to an insecure URL.")
            data = response.read(limit + 1)
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            raise UpdateError("GitHub API rate limit reached. Try again later.") from exc
        raise UpdateError(f"GitHub returned HTTP {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise UpdateError("Cannot reach GitHub. Check your connection and try again.") from exc
    if len(data) > limit:
        raise UpdateError("Release metadata is unexpectedly large.")
    return data


@dataclass(frozen=True)
class Release:
    version: str
    release: str
    notes: str
    size: int
    url: str
    checksum_url: str
    asset_name: str
    arch: str


def check_release() -> tuple[tuple[str, str, str], Release | None]:
    current = installed_evr()
    arch = run("rpm", "--eval", "%{_arch}")
    if arch not in {"x86_64", "aarch64", "noarch"}:
        raise UpdateError(f"Unsupported system architecture: {arch}.")
    try:
        release = json.loads(fetch(API))
    except (ValueError, TypeError) as exc:
        raise UpdateError("GitHub returned invalid release metadata.") from exc
    if release.get("draft") or release.get("prerelease"):
        raise UpdateError("The latest release is not stable.")
    version = release.get("tag_name", "").removeprefix("v")
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}", version):
        raise UpdateError("The latest release has an invalid version tag.")
    assets = {a.get("name"): a for a in release.get("assets", []) if isinstance(a, dict)}
    choices = []
    for name, asset in assets.items():
        if not isinstance(name, str):
            continue
        match = re.fullmatch(rf"{PACKAGE}-{re.escape(version)}-([0-9][A-Za-z0-9._~+]*)\.(noarch|{re.escape(arch)})\.rpm", name)
        if match:
            choices.append((name, asset, match.group(1), match.group(2)))
    if not choices:
        if rpm_version_compare(("0", version, "0"), current) <= 0:
            return current, None
        raise UpdateError(f"Release {version} has no RPM for {arch}.")
    choices.sort(key=lambda choice: choice[3] != arch)
    name, asset, rpm_release, asset_arch = choices[0]
    if rpm_version_compare(("0", version, rpm_release), current) <= 0:
        return current, None
    checksums = assets.get("SHA256SUMS")
    if not checksums:
        raise UpdateError("Release is missing SHA256SUMS.")
    url = asset.get("browser_download_url", "")
    checksum_url = checksums.get("browser_download_url", "")
    official = f"https://github.com/CytheCy/md_pad/releases/download/{release['tag_name']}/"
    if url != official + name or checksum_url != official + "SHA256SUMS":
        raise UpdateError("Release asset URL is unexpected.")
    size = asset.get("size", 0)
    if not isinstance(size, int) or size < 1 or size > MAX_RPM:
        raise UpdateError("Release RPM size is invalid.")
    return current, Release(version, rpm_release, release.get("body") or "No release notes.",
                            size, url, checksum_url, name, asset_arch)


def verify_rpm(path: Path, release: Release, current: tuple[str, str, str]) -> None:
    if not KEY.is_file():
        raise UpdateError("MDPad release signing key is missing from this installation.")
    # An isolated RPM keyring admits only the key shipped in the installed application.
    with tempfile.TemporaryDirectory(prefix="mdpad-rpmdb-") as db:
        run("rpmkeys", "--dbpath", db, "--import", str(KEY))
        result = run("rpmkeys", "--dbpath", db, "--checksig", "--verbose", str(path))
        if not re.search(r"signature[^\n]*:\s*OK\b", result, re.I):
            raise UpdateError("RPM is unsigned or its signing key is not trusted.")
    fields = run("rpm", "-qp", "--qf", "%{NAME}\n%{EPOCHNUM}\n%{VERSION}\n%{RELEASE}\n%{ARCH}\n", str(path)).splitlines()
    if len(fields) != 5 or fields[0] != PACKAGE or fields[2] != release.version or fields[3] != release.release or fields[4] != release.arch:
        raise UpdateError("RPM package identity, version, or architecture does not match the release.")
    if rpm_version_compare(tuple(fields[1:4]), current) <= 0:
        raise UpdateError("The RPM would not upgrade the installed package.")


def release_checksum(checksums: str, asset_name: str) -> str:
    # Older releases used sha256sum ./..., while newer ones use bare filenames.
    pattern = rf"^([0-9a-fA-F]{{64}})[ \t]+\*?(?:\./)?{re.escape(asset_name)}$"
    matches = re.findall(pattern, checksums, re.M)
    if len(matches) != 1:
        raise UpdateError("The release checksum is missing or ambiguous.")
    return matches[0].lower()


class Worker(QThread):
    checked = Signal(object, object)
    ready = Signal(str, object)
    progress = Signal(int)
    failed = Signal(str)

    def __init__(self, release: Release | None = None, current=None, parent=None):
        super().__init__(parent)
        self.release = release
        self.current = current
        self.cancelled = threading.Event()

    def run(self):
        try:
            if self.release is None:
                self.checked.emit(*check_release())
            else:
                self.download()
        except UpdateError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"Update failed: {exc}")

    def download(self):
        release = self.release
        assert release is not None
        checksums = fetch(release.checksum_url).decode("utf-8")
        expected_digest = release_checksum(checksums, release.asset_name)
        directory = Path(tempfile.mkdtemp(prefix="mdpad-update-"))
        path = directory / release.asset_name
        try:
            req = urllib.request.Request(release.url, headers={"User-Agent": "MDPad-updater"})
            digest = hashlib.sha256()
            received = 0
            try:
                with urllib.request.urlopen(req, timeout=30) as source, path.open("xb") as target:
                    if not source.geturl().startswith("https://"):
                        raise UpdateError("RPM redirected to an insecure URL.")
                    while chunk := source.read(256 * 1024):
                        if self.cancelled.is_set():
                            raise UpdateError("Download cancelled.")
                        received += len(chunk)
                        if received > release.size or received > MAX_RPM:
                            raise UpdateError("RPM exceeds the advertised size.")
                        target.write(chunk)
                        digest.update(chunk)
                        self.progress.emit(min(100, received * 100 // release.size))
            except (urllib.error.URLError, TimeoutError) as exc:
                raise UpdateError("Download failed. Check your connection and try again.") from exc
            if received != release.size or digest.hexdigest().lower() != expected_digest:
                raise UpdateError("RPM size or SHA-256 checksum does not match the release.")
            verify_rpm(path, release, self.current)
            self.ready.emit(str(path), release)
        except Exception:
            shutil.rmtree(directory, ignore_errors=True)
            raise


class UpdatesDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.release = None
        self.current = None
        self.worker = None
        self.path = None
        self.setWindowTitle("Updates")
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)
        self.installed = QLabel("Installed version: checking…")
        self.available = QLabel("Available version: —")
        self.status = QLabel("Press Check for Updates to contact GitHub.")
        self.status.setWordWrap(True)
        self.notes = QTextEdit()
        self.notes.setReadOnly(True)
        self.notes.setPlaceholderText("Release notes will appear here.")
        self.notes.setMinimumHeight(180)
        self.bar = QProgressBar()
        self.bar.hide()
        self.check_button = QPushButton("Check for Updates")
        self.install_button = QPushButton("Install Update")
        self.install_button.hide()
        self.cancel_button = QPushButton("Cancel Download")
        self.cancel_button.hide()
        for widget in (self.installed, self.available, self.status, self.notes, self.bar,
                       self.check_button, self.install_button, self.cancel_button):
            layout.addWidget(widget)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)
        self.check_button.clicked.connect(self.check)
        self.install_button.clicked.connect(self.install)
        self.cancel_button.clicked.connect(lambda: self.worker.cancelled.set())
        try:
            self.installed.setText(f"Installed version: {installed_evr()[1]}")
        except UpdateError:
            self.installed.setText("Installed RPM: unavailable (install MDPad using DNF first)")

    def start_worker(self, worker):
        self.worker = worker
        self.check_button.setEnabled(False)
        self.install_button.setEnabled(False)
        worker.failed.connect(self.on_error)
        worker.finished.connect(lambda: self.check_button.setEnabled(True))
        worker.start()

    def check(self):
        self.status.setText("Checking GitHub Releases…")
        self.install_button.hide()
        worker = Worker(parent=self)
        worker.checked.connect(self.on_checked)
        self.start_worker(worker)

    def on_checked(self, current, release):
        self.current, self.release = current, release
        self.installed.setText(f"Installed version: {current[1]}-{current[2]}")
        if release is None:
            self.available.setText("Available version: —")
            self.status.setText("You're up to date.")
            self.notes.clear()
            return
        self.available.setText(f"Available version: {release.version}-{release.release}")
        self.status.setText(f"Download size: {release.size / (1024 * 1024):.1f} MiB")
        self.notes.setPlainText(release.notes)
        self.install_button.show()
        self.install_button.setEnabled(True)

    def install(self):
        self.status.setText("Downloading and verifying the signed RPM…")
        self.bar.setValue(0)
        self.bar.show()
        self.cancel_button.show()
        worker = Worker(self.release, self.current, self)
        worker.progress.connect(self.bar.setValue)
        worker.ready.connect(self.on_ready)
        self.start_worker(worker)

    def on_error(self, message):
        self.status.setText(message)
        self.cancel_button.hide()
        self.install_button.setEnabled(self.release is not None)

    def on_ready(self, path, release):
        self.path = path
        self.cancel_button.hide()
        self.status.setText("Verified. Close MDPad to start the DNF upgrade.")
        if not self.window.confirm_discard():
            self.status.setText("Installation cancelled; save your note and try again.")
            self.install_button.setEnabled(True)
            return
        self.window.settings.sync()
        helper = Path(__file__).with_name("update_helper.py")
        try:
            subprocess.Popen(["/usr/bin/python3", str(helper), path],
                             start_new_session=True, close_fds=True)
        except OSError as exc:
            self.status.setText(f"Could not start updater: {exc}")
            self.install_button.setEnabled(True)
            return
        self.window._updating = True
        self.window.close()
        self.close()

    def closeEvent(self, event):  # noqa: N802
        if self.worker and self.worker.isRunning():
            self.worker.cancelled.set()
            self.worker.wait(2000)
            if self.worker.isRunning():
                event.ignore()
                return
        super().closeEvent(event)
