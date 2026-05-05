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
        self.assertNotIn("does not install OpenWhispr", install)

    def test_readme_documents_openwhispr_install_and_tested_ubuntu_version(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("./install.sh --no-openwhispr", readme)
        self.assertIn("Ubuntu 22.04.5 LTS", readme)
        self.assertIn("downloads the default STT model", readme)


if __name__ == "__main__":
    unittest.main()
