import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import whisprflowctl


class ConfigCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old_xdg = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = self.tmp.name

    def tearDown(self):
        if self.old_xdg is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self.old_xdg

    def read_config(self):
        return json.loads((Path(self.tmp.name) / "whisprflow" / "config.json").read_text(encoding="utf-8"))

    def test_config_set_writes_json_value(self):
        code = whisprflowctl.main(["config", "set", "streaming_phrases", "false"])

        self.assertEqual(code, 0)
        self.assertFalse(self.read_config()["streaming_phrases"])

    def test_config_set_writes_string_value(self):
        code = whisprflowctl.main(["config", "set", "mic_device", "alsa_input.example"])

        self.assertEqual(code, 0)
        self.assertEqual(self.read_config()["mic_device"], "alsa_input.example")

    def test_config_unset_removes_override(self):
        whisprflowctl.main(["config", "set", "mic_device", "alsa_input.example"])

        code = whisprflowctl.main(["config", "unset", "mic_device"])

        self.assertEqual(code, 0)
        self.assertNotIn("mic_device", self.read_config())


class CommandCliTests(unittest.TestCase):
    def test_service_restart_runs_systemctl_user(self):
        with mock.patch("whisprflowctl.run_command", return_value=0) as run:
            code = whisprflowctl.main(["service", "restart"])

        self.assertEqual(code, 0)
        run.assert_called_once_with(["systemctl", "--user", "restart", "whisprflow.service"], check=False)

    def test_model_install_uses_known_model_url(self):
        with mock.patch("whisprflowctl.download_model", return_value=0) as download:
            code = whisprflowctl.main(["model", "install", "large-v3-turbo"])

        self.assertEqual(code, 0)
        download.assert_called_once_with("large-v3-turbo")

    def test_openwhispr_pin_sets_ref(self):
        with mock.patch("whisprflowctl.run_command", return_value=0) as run:
            code = whisprflowctl.main(["openwhispr", "pin", "abc123"])

        self.assertEqual(code, 0)
        run.assert_any_call(["git", "-C", str(Path.home() / "openwhispr"), "fetch", "--tags", "origin"])
        run.assert_any_call(["git", "-C", str(Path.home() / "openwhispr"), "checkout", "abc123"])

    def test_doctor_reports_missing_and_present_dependencies(self):
        with mock.patch("whisprflowctl.shutil.which", return_value="/usr/bin/fake"):
            with mock.patch("whisprflowctl.Path.exists", return_value=True):
                with mock.patch("whisprflowctl.Path.is_file", return_value=True):
                    with mock.patch("whisprflowctl.Path.is_dir", return_value=True):
                        code = whisprflowctl.main(["doctor"])

        self.assertEqual(code, 0)

    def test_openwhispr_server_path_prefers_packaged_dist_binary(self):
        dist_path = Path.home() / "openwhispr" / "dist" / "linux-unpacked" / "resources" / "bin" / "whisper-server-linux-x64"

        with mock.patch("whisprflowctl.Path.exists", return_value=True):
            self.assertEqual(whisprflowctl.openwhispr_server_path(), dist_path)


if __name__ == "__main__":
    unittest.main()
