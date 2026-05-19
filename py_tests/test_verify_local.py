import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_local.ps1"


class VerifyLocalScriptTestCase(unittest.TestCase):
    def test_verification_script_uses_step_list(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("$verificationSteps = @(", content)
        self.assertIn("foreach ($step in $verificationSteps)", content)
        self.assertIn("& $step.Command @arguments", content)

    def test_script_runs_python_module_commands(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn('Name      = "format check"', content)
        self.assertIn('Arguments = @("-m", "ruff", "format", "--check", ".")', content)
        self.assertIn('Arguments = @("-m", "ruff", "check", ".")', content)
        self.assertIn('Arguments = @("-m", "mypy")', content)
        self.assertIn('Arguments = @("-m", "pytest", "py_tests", "-q")', content)

    def test_script_places_python_bytecode_cache_under_cache_root(self):
        content = SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn('$cacheRoot = Join-Path $projectRoot ".cache"', content)
        self.assertIn('$env:PYTHONPYCACHEPREFIX = Join-Path $cacheRoot "pycache"', content)
        self.assertIn("New-Item -ItemType Directory -Path $env:PYTHONPYCACHEPREFIX -Force", content)


if __name__ == "__main__":
    unittest.main()
