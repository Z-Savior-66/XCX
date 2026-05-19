import tomllib
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"
GITIGNORE_PATH = PROJECT_ROOT / ".gitignore"


class ToolCacheConfigTestCase(unittest.TestCase):
    def test_python_tool_caches_are_under_cache_root(self):
        config = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))

        self.assertEqual(config["tool"]["ruff"]["cache-dir"], ".cache/ruff")
        self.assertEqual(config["tool"]["pytest"]["ini_options"]["cache_dir"], ".cache/pytest")
        self.assertEqual(config["tool"]["mypy"]["cache_dir"], ".cache/mypy")

    def test_cache_root_is_ignored_and_excluded_from_ruff(self):
        config = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
        gitignore = GITIGNORE_PATH.read_text(encoding="utf-8")

        self.assertIn(".cache", config["tool"]["ruff"]["exclude"])
        self.assertIn(".cache/", gitignore)


if __name__ == "__main__":
    unittest.main()
