import ast
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent


def default_config_from(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    constants = {}
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = [node.target] if isinstance(node, ast.AnnAssign) else node.targets
            for target in targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id
                    in {"APP_DIR_NAME", "CONFIG_DIR_NAME", "LEGACY_CONFIG_DIR_NAME"}
                ):
                    constants[target.id] = ast.literal_eval(node.value)

    env = {"Path": Path, **constants}
    for node in tree.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "DEFAULT_CONFIG"
        ):
            return eval(
                compile(ast.Expression(node.value), str(path), "eval"),
                {"__builtins__": {"str": str}},
                env,
            )

    raise AssertionError(f"DEFAULT_CONFIG not found in {path}")


def normalize_config_for_example(config):
    config = dict(config)
    for key in ("keep_failed_wav", "status_file", "hud_file"):
        config[key] = None
    return config


class PackagingTests(unittest.TestCase):
    def test_installer_can_install_openwhispr_and_model(self):
        install = (ROOT / "install.sh").read_text(encoding="utf-8")

        self.assertIn("--no-openwhispr", install)
        self.assertIn("download:whisper-cpp", install)
        self.assertIn("huggingface.co/ggerganov/whisper.cpp", install)
        self.assertIn("nvm install", install)
        self.assertIn("package.json", install)
        self.assertIn("OPENWHISPR_REF", install)
        self.assertIn("whisprflowctl", install)
        self.assertIn("git -C \"$OPENWHISPR_ROOT\" checkout", install)
        self.assertIn("--setup", install)
        self.assertIn("RUN_SETUP", install)
        self.assertIn("setup wizard", install)
        self.assertNotIn("does not install OpenWhispr", install)

    def test_readme_documents_openwhispr_install_and_tested_ubuntu_version(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("./install.sh --no-openwhispr", readme)
        self.assertIn("Ubuntu 22.04.5 LTS", readme)
        self.assertIn("downloads the default STT model", readme)
        self.assertIn("OPENWHISPR_REF", readme)
        self.assertIn("whisprflowctl doctor", readme)
        self.assertIn("whisprflowctl setup wizard", readme)
        self.assertIn("whisprflowctl test button", readme)
        self.assertIn("whisprflowctl calibrate --apply", readme)
        self.assertIn("./install.sh --setup", readme)
        self.assertIn("CHANGELOG.md", readme)
        self.assertIn("whisprflowctl test sources --prep-seconds 3", readme)
        self.assertIn("configured button source stayed flat", readme)

    def test_changelog_documents_release_history(self):
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

        for version in ("v0.3.0", "v0.3.1", "v0.3.2", "v0.3.3", "v0.3.4"):
            self.assertIn(version, changelog)

    def test_recording_duration_cap_is_not_documented_or_configured(self):
        for path in ("README.md", "config.example.json", "whisprflowctl.py"):
            content = (ROOT / path).read_text(encoding="utf-8")
            self.assertNotIn("max_recording_sec", content)
            self.assertNotIn("max recording duration", content)

    def test_example_config_matches_runtime_defaults(self):
        example_config = normalize_config_for_example(
            json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
        )

        self.assertEqual(
            example_config,
            normalize_config_for_example(default_config_from(ROOT / "whisprflow.py")),
        )
        self.assertEqual(
            example_config,
            normalize_config_for_example(default_config_from(ROOT / "whisprflowctl.py")),
        )

    def test_ci_runs_unit_shell_and_secret_checks(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

        self.assertIn("python -m unittest", workflow)
        self.assertIn("bash -n", workflow)
        self.assertIn("grep", workflow)
        self.assertIn("test_whisprflowctl.py", workflow)


if __name__ == "__main__":
    unittest.main()
