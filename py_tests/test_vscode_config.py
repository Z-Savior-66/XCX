import json
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LAUNCH_PATH = PROJECT_ROOT / ".vscode" / "launch.json"
VENV_PYTHON = "${workspaceFolder}\\.venv\\Scripts\\python.exe"


class VscodeConfigTestCase(unittest.TestCase):
    def test_debug_configs_use_project_virtualenv_python(self):
        launch = json.loads(LAUNCH_PATH.read_text(encoding="utf-8"))

        for config in launch["configurations"]:
            if config.get("type") != "debugpy":
                continue
            with self.subTest(config=config["name"]):
                self.assertEqual(config.get("python"), VENV_PYTHON)


if __name__ == "__main__":
    unittest.main()
