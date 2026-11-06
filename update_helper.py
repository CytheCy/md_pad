#!/usr/bin/python3
"""Separate process that runs the authorized DNF transaction after MDPad exits."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QProcess, QTimer
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton, QTextEdit, QVBoxLayout

from updater import KEY, PACKAGE, installed_evr, rpm_version_compare, run


class Installer(QDialog):
    def __init__(self, rpm_path: Path):
        super().__init__()
        self.rpm_path = rpm_path
        self.setWindowTitle("Updating MDPad")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        self.status = QLabel("Waiting for MDPad to close…")
        layout.addWidget(self.status)
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output)
        self.restart = QPushButton("Restart MDPad")
        self.restart.setEnabled(False)
        self.restart.clicked.connect(self.relaunch)
        layout.addWidget(self.restart)
        self.process = None
        self.stage = 0
        QTimer.singleShot(1200, self.start)

    def start(self):
        try:
            if not self.rpm_path.is_file() or not KEY.is_file():
                raise ValueError("The downloaded RPM or release key is missing.")
            if self.rpm_path.parent.stat().st_uid != os.getuid():
                raise ValueError("The download directory has an unexpected owner.")
            self.before = installed_evr()
            self.target = run("rpm", "-qp", "--qf", "%{EPOCHNUM}\n%{VERSION}\n%{RELEASE}\n", str(self.rpm_path)).splitlines()
            if rpm_version_compare(tuple(self.target), self.before) <= 0:
                raise ValueError("The RPM is not newer than the installed version.")
        except Exception as exc:
            self.fail(str(exc))
            return
        self.status.setText("Requesting administrator authorization to trust the MDPad release key…")
        self.run_command(["/usr/bin/pkexec", "/usr/bin/rpmkeys", "--import", str(KEY)])

    def run_command(self, args):
        self.process = QProcess(self)
        self.process.setProgram(args[0])
        self.process.setArguments(args[1:])
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.readyReadStandardError.connect(self.read_output)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(lambda _: self.fail(self.process.errorString()))
        self.process.start()

    def read_output(self):
        if self.process:
            content = bytes(self.process.readAllStandardOutput()) + bytes(self.process.readAllStandardError())
            if content:
                self.output.append(content.decode(errors="replace"))

    def finished(self, code, _status):
        self.read_output()
        if code:
            self.fail("Authorization or package installation failed. The previous version remains installed unless DNF reports otherwise.")
            return
        if self.stage == 0:
            self.stage = 1
            self.status.setText("Installing with DNF5. This may take a moment…")
            self.run_command(["/usr/bin/pkexec", "/usr/bin/dnf5", "--setopt=localpkg_gpgcheck=1",
                              "upgrade", "-y", str(self.rpm_path)])
            return
        try:
            after = installed_evr()
            if rpm_version_compare(after, self.before) <= 0 or after[1:] != tuple(self.target[1:]):
                raise ValueError("DNF completed, but the installed version is not the expected update.")
        except Exception as exc:
            self.fail(str(exc))
            return
        self.status.setText("Update installed. You can restart MDPad now.")
        self.restart.setEnabled(True)
        shutil.rmtree(self.rpm_path.parent, ignore_errors=True)

    def fail(self, message):
        self.status.setText(message)
        self.restart.setEnabled(True)
        self.output.append(message)

    def relaunch(self):
        subprocess.Popen(["/usr/bin/pad"], start_new_session=True, close_fds=True)
        self.close()

    def closeEvent(self, event):  # noqa: N802
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            self.status.setText("The DNF transaction is still running. Wait for it to finish.")
            event.ignore()
            return
        super().closeEvent(event)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(2)
    app = QApplication(sys.argv)
    dialog = Installer(Path(sys.argv[1]))
    dialog.show()
    raise SystemExit(app.exec())
