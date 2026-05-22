import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from desktop_py.core.startup import (
    APP_NAME,
    RUN_KEY_PATH,
    StartupUnavailableError,
    get_startup_enabled,
    set_startup_enabled,
    startup_command,
)


class FakeRegistry:
    HKEY_CURRENT_USER = object()
    KEY_READ = 1
    KEY_SET_VALUE = 2
    REG_SZ = 1

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def OpenKey(self, _root: object, path: str, _reserved: int, _access: int) -> str:
        if path != RUN_KEY_PATH:
            raise OSError("未知启动项路径")
        return path

    def CreateKeyEx(self, _root: object, path: str, _reserved: int, _access: int) -> str:
        if path != RUN_KEY_PATH:
            raise OSError("未知启动项路径")
        return path

    def QueryValueEx(self, _key: str, value_name: str) -> tuple[str, int]:
        if value_name not in self.values:
            raise OSError("启动项不存在")
        return self.values[value_name], self.REG_SZ

    def SetValueEx(self, _key: str, value_name: str, _reserved: int, _value_type: int, value: str) -> None:
        self.values[value_name] = value

    def DeleteValue(self, _key: str, value_name: str) -> None:
        if value_name not in self.values:
            raise OSError("启动项不存在")
        del self.values[value_name]

    def CloseKey(self, _key: str) -> None:
        return


class StartupTestCase(unittest.TestCase):
    def test_startup_command_uses_pythonw_and_desktop_main_in_development(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            python = root / "python.exe"
            pythonw = root / "pythonw.exe"
            script = root / "desktop_main.py"
            python.write_text("", encoding="utf-8")
            pythonw.write_text("", encoding="utf-8")
            script.write_text("", encoding="utf-8")

            command = startup_command(executable_path=python, script_path=script, frozen=False, os_name="nt")

        self.assertIn("pythonw.exe", command)
        self.assertIn("desktop_main.py", command)

    def test_startup_command_uses_executable_when_frozen(self):
        command = startup_command(
            executable_path=Path("C:/Program Files/XCX/小程序工具.exe"), frozen=True, os_name="nt"
        )

        self.assertIn("小程序工具.exe", command)
        self.assertNotIn("desktop_main.py", command)

    def test_set_and_get_startup_enabled_use_current_user_run_key(self):
        registry = FakeRegistry()

        set_startup_enabled(True, command="C:/app/app.exe", registry=registry, os_name="nt")

        self.assertTrue(get_startup_enabled(registry=registry, os_name="nt"))
        self.assertEqual(registry.values[APP_NAME], "C:/app/app.exe")

    def test_set_startup_disabled_removes_run_value(self):
        registry = FakeRegistry()
        registry.values[APP_NAME] = "C:/app/app.exe"

        set_startup_enabled(False, registry=registry, os_name="nt")

        self.assertFalse(get_startup_enabled(registry=registry, os_name="nt"))

    def test_non_windows_read_is_false_and_write_is_unavailable(self):
        self.assertFalse(get_startup_enabled(os_name="posix"))

        with self.assertRaises(StartupUnavailableError):
            set_startup_enabled(True, os_name="posix")


if __name__ == "__main__":
    unittest.main()
