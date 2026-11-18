"""Exercise real event-loop shutdown and interpreter cleanup in fresh processes."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest


class ShutdownTests(unittest.TestCase):
    def test_shutdown_releases_window_before_interpreter_finalization(self):
        script = textwrap.dedent('''\
            import gc
            import sys
            from unittest.mock import patch
            from PySide6.QtCore import QTimer
            from PySide6.QtWidgets import QApplication, QMessageBox
            from shiboken6 import isValid
            import main

            windows = []
            destroyed = []
            mode = sys.argv[1]
            source = ('# First\\nMissspelled prose\\n## Second\\n'
                      '```\\ncode\\n```\\n| A | B |\\n| - | - |\\n| C | D |')
            show = main.MainWindow.show

            def prepare(window):
                windows.append(window)
                window.destroyed.connect(lambda: destroyed.append(True))
                window.editor.setPlainText(source)
                window.editor.spelling.refresh()
                window.open_find()
                window.find_input.setText('code')
                window.set_theme('tokyo-night')
                show(window)
                QTimer.singleShot(50, finish)

            def finish():
                window = windows[0]
                if mode == 'quit':
                    with patch.object(QMessageBox, 'exec',
                                      return_value=QMessageBox.StandardButton.Discard):
                        QApplication.instance().quit()
                    return
                with patch.object(QMessageBox, 'exec',
                                  return_value=QMessageBox.StandardButton.Cancel):
                    assert not window.close()
                assert window.editor.toPlainText() == source
                assert isValid(window)
                with patch.object(QMessageBox, 'exec',
                                  return_value=QMessageBox.StandardButton.Discard):
                    assert window.close()

            with (patch.object(main.MainWindow, 'show', prepare),
                  patch.object(sys, 'argv', ['main.py'])):
                result = main.main()
            assert result == 0
            assert destroyed == [True], 'window survived the event loop'
            assert not isValid(windows[0])
            windows.clear()
            gc.collect()
            print('shutdown complete', flush=True)
        ''')
        for mode in ('close', 'quit'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as root:
                env = os.environ | {
                    'QT_QPA_PLATFORM': 'offscreen',
                    'XDG_CONFIG_HOME': root,
                    'XDG_DATA_HOME': root,
                    'XDG_STATE_HOME': root,
                    'PYTHONFAULTHANDLER': '1',
                }
                result = subprocess.run(
                    [sys.executable, '-c', script, mode],
                    cwd=Path(__file__).resolve().parents[1], env=env,
                    capture_output=True, text=True, timeout=20,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('shutdown complete', result.stdout)
                self.assertNotIn('Traceback', result.stderr)
