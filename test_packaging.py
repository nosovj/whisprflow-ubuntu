from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent


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

    def test_ci_runs_unit_shell_and_secret_checks(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

        self.assertIn("python -m unittest", workflow)
        self.assertIn("bash -n", workflow)
        self.assertIn("grep", workflow)
        self.assertIn("test_whisprflowctl.py", workflow)


if __name__ == "__main__":
    unittest.main()
