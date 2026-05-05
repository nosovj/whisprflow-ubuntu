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

    def test_config_set_rejects_wrong_known_type(self):
        code = whisprflowctl.main(["config", "set", "mic_min_mean_abs", "not-a-number"])

        self.assertEqual(code, 2)
        self.assertFalse((Path(self.tmp.name) / "whisprflow" / "config.json").exists())

    def test_config_validate_accepts_current_defaults(self):
        code = whisprflowctl.main(["config", "validate"])

        self.assertEqual(code, 0)

    def test_config_validate_rejects_bad_existing_value(self):
        whisprflowctl.save_config({"mic_min_mean_abs": "not-a-number"})

        code = whisprflowctl.main(["config", "validate"])

        self.assertEqual(code, 1)


class AnalysisTests(unittest.TestCase):
    def test_button_analysis_recommends_thresholds_for_clear_press(self):
        samples = [(100, 300), (120, 350), (140, 400), (4200, 12500), (4500, 13000), (4600, 12800)]

        result = whisprflowctl.analyze_button_levels(samples)

        self.assertEqual(result["verdict"], "good")
        self.assertGreater(result["recommendations"]["button_threshold"], 1000)
        self.assertGreater(result["recommendations"]["button_peak_threshold"], 3000)

    def test_button_analysis_reports_no_press(self):
        samples = [(100, 300), (120, 350), (140, 400), (130, 360)]

        result = whisprflowctl.analyze_button_levels(samples)

        self.assertEqual(result["verdict"], "button not detected")
        self.assertEqual(result["recommendations"], {})

    def test_mic_analysis_reports_speech_not_detected(self):
        samples = [(30, 80), (35, 90), (40, 100), (80, 300), (90, 350), (95, 360)]

        result = whisprflowctl.analyze_mic_levels(samples)

        self.assertEqual(result["verdict"], "speech not detected")
        self.assertEqual(result["recommendations"], {})

    def test_mic_analysis_reports_quiet_speech(self):
        samples = [(30, 80), (35, 90), (40, 100), (150, 2800), (160, 3000), (170, 3200)]

        result = whisprflowctl.analyze_mic_levels(samples)

        self.assertEqual(result["verdict"], "mic too quiet")

    def test_mic_analysis_recommends_speech_thresholds(self):
        samples = [(40, 120), (50, 150), (60, 180), (900, 7000), (950, 7200), (1000, 7600)]

        result = whisprflowctl.analyze_mic_levels(samples)

        self.assertEqual(result["verdict"], "good")
        self.assertGreater(result["recommendations"]["mic_speech_threshold"], 100)


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
                with mock.patch("whisprflowctl.load_config", return_value={"button_device": "button", "mic_device": "mic"}):
                    code = whisprflowctl.main(["doctor"])

        self.assertEqual(code, 0)

    def test_openwhispr_server_path_prefers_packaged_dist_binary(self):
        dist_path = Path.home() / "openwhispr" / "dist" / "linux-unpacked" / "resources" / "bin" / "whisper-server-linux-x64"

        with mock.patch("whisprflowctl.Path.exists", return_value=True):
            self.assertEqual(whisprflowctl.openwhispr_server_path(), dist_path)

    def test_summary_command_loads_current_config(self):
        with mock.patch("whisprflowctl.load_config", return_value=whisprflowctl.DEFAULT_CONFIG.copy()):
            code = whisprflowctl.main(["summary"])

        self.assertEqual(code, 0)

    def test_test_button_uses_sampled_levels(self):
        with mock.patch("whisprflowctl.load_config", return_value={"button_device": "button", "sample_rate": 16000}):
            with mock.patch("whisprflowctl.sample_parecord_levels", return_value=[(100, 200), (4000, 9000)]):
                code = whisprflowctl.main(["test", "button", "--seconds", "1"])

        self.assertEqual(code, 0)

    def test_test_button_returns_nonzero_when_not_detected(self):
        with mock.patch("whisprflowctl.load_config", return_value={"button_device": "button", "sample_rate": 16000}):
            with mock.patch("whisprflowctl.sample_parecord_levels", return_value=[(100, 200), (110, 210)]):
                code = whisprflowctl.main(["test", "button", "--seconds", "1"])

        self.assertEqual(code, 1)

    def test_calibrate_apply_saves_recommendations_and_restarts(self):
        cfg = {
            "button_device": "button",
            "mic_device": "mic",
            "sample_rate": 16000,
            "button_chunk_size": 1600,
        }
        samples = [[(100, 200), (4000, 9000), (4200, 9200)], [(40, 100), (900, 7000), (950, 7200)]]

        with mock.patch("whisprflowctl.load_config", return_value=cfg.copy()):
            with mock.patch("whisprflowctl.sample_parecord_levels", side_effect=samples):
                with mock.patch("whisprflowctl.save_config") as save:
                    with mock.patch("whisprflowctl.run_command", return_value=0) as run:
                        code = whisprflowctl.main(["calibrate", "--apply", "--seconds", "1"])

        self.assertEqual(code, 0)
        self.assertTrue(save.called)
        run.assert_called_once_with(["systemctl", "--user", "restart", "whisprflow.service"], check=False)


if __name__ == "__main__":
    unittest.main()
