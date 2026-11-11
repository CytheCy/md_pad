"""The updater advances after an authorized command exits."""

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from update_helper import Installer


class UpdateHelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_key_import_completion_starts_dnf_stage(self):
        with patch('update_helper.QTimer.singleShot'):
            dialog = Installer(Path('/tmp/no-update.rpm'))
        loop = QEventLoop()
        original = dialog.run_command
        commands = []

        def capture(args):
            commands.append(args)
            if len(commands) == 1:
                original(['/usr/bin/true'])
            else:
                loop.quit()

        dialog.run_command = capture
        capture(['/usr/bin/pkexec', '/usr/bin/rpmkeys', '--import', '/tmp/key'])
        QTimer.singleShot(1000, loop.quit)
        loop.exec()

        self.assertEqual(dialog.stage, 1)
        self.assertEqual(commands[1][:3], ['/usr/bin/pkexec', '/usr/bin/dnf5', '--setopt=localpkg_gpgcheck=1'])
        dialog.close()


if __name__ == '__main__':
    unittest.main()
