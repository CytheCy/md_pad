"""Security and failure-path tests for user initiated updates."""

import json
import io
import urllib.error
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import updater


class UpdaterTests(unittest.TestCase):
    def test_cancelled_download_stops_before_verification(self):
        release = updater.Release("1.0.1", "1.fc44", "", 4,
            "https://github.com/CytheCy/md_pad/releases/download/v1.0.1/md-pad-1.0.1-1.fc44.noarch.rpm",
            "https://github.com/CytheCy/md_pad/releases/download/v1.0.1/SHA256SUMS",
            "md-pad-1.0.1-1.fc44.noarch.rpm", "noarch")
        class Response(io.BytesIO):
            def geturl(self):
                return release.url
        worker = updater.Worker(release, ("0", "1.0.0", "1.fc44"))
        worker.cancelled.set()
        checksum = ("a" * 64 + "  " + release.asset_name).encode()
        with patch.object(updater, "fetch", return_value=checksum), \
             patch.object(updater.urllib.request, "urlopen", return_value=Response(b"data")), \
             patch.object(updater, "verify_rpm") as verify:
            with self.assertRaisesRegex(updater.UpdateError, "cancelled"):
                worker.download()
            verify.assert_not_called()

    def test_failed_download_reports_network_error(self):
        release = updater.Release("1.0.1", "1.fc44", "", 4,
            "https://github.com/CytheCy/md_pad/releases/download/v1.0.1/md-pad-1.0.1-1.fc44.noarch.rpm",
            "https://github.com/CytheCy/md_pad/releases/download/v1.0.1/SHA256SUMS",
            "md-pad-1.0.1-1.fc44.noarch.rpm", "noarch")
        worker = updater.Worker(release, ("0", "1.0.0", "1.fc44"))
        checksum = ("a" * 64 + "  " + release.asset_name).encode()
        with patch.object(updater, "fetch", return_value=checksum), \
             patch.object(updater.urllib.request, "urlopen", side_effect=urllib.error.URLError("offline")):
            with self.assertRaisesRegex(updater.UpdateError, "Download failed"):
                worker.download()

    def test_offline_check_gives_actionable_error(self):
        with patch.object(updater, "installed_evr", return_value=("0", "1.0.0", "1.fc44")), \
             patch.object(updater, "run", return_value="x86_64"), \
             patch.object(updater, "fetch", side_effect=updater.UpdateError("Cannot reach GitHub.")):
            with self.assertRaisesRegex(updater.UpdateError, "Cannot reach GitHub"):
                updater.check_release()

    def test_newer_release_without_matching_rpm_is_reported(self):
        release = {"tag_name": "v1.0.1", "draft": False, "prerelease": False, "assets": []}
        with patch.object(updater, "installed_evr", return_value=("0", "1.0.0", "1.fc44")), \
             patch.object(updater, "run", return_value="x86_64"), \
             patch.object(updater, "fetch", return_value=json.dumps(release).encode()):
            with self.assertRaisesRegex(updater.UpdateError, "no RPM for x86_64"):
                updater.check_release()

    def test_unsigned_rpm_is_rejected_before_metadata_query(self):
        release = updater.Release("1.0.1", "1.fc44", "", 100, "", "", "md-pad-1.0.1-1.fc44.noarch.rpm", "noarch")
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(updater, "run", return_value="Header SHA256 digest: OK\nPayload SHA256 digest: OK") as command:
            with self.assertRaisesRegex(updater.UpdateError, "unsigned"):
                updater.verify_rpm(Path(directory) / release.asset_name, release, ("0", "1.0.0", "1.fc44"))
            self.assertFalse(any(call.args[1] == "-qp" for call in command.call_args_list))


if __name__ == "__main__":
    unittest.main()
