import unittest
from unittest.mock import patch

from desktop_dev import ROOT, find_existing_app_pids, spawn_app


class DesktopDevTestCase(unittest.TestCase):
    def test_find_existing_app_pids_only_matches_desktop_main(self):
        processes = [
            {"ProcessId": 100, "CommandLine": r"python.exe desktop_main.py"},
            {"ProcessId": 101, "CommandLine": r"python.exe desktop_dev.py"},
            {"ProcessId": 102, "CommandLine": r"python.exe -m unittest py_tests.test_app -v"},
            {"ProcessId": 103, "CommandLine": r"python.exe C:\Users\Administrator\Desktop\M\desktop_main.py"},
        ]

        result = find_existing_app_pids(processes, current_pid=101)

        self.assertEqual(result, [100, 103])

    def test_find_existing_app_pids_skips_current_process(self):
        processes = [
            {"ProcessId": 200, "CommandLine": r"python.exe desktop_main.py"},
        ]

        result = find_existing_app_pids(processes, current_pid=200)

        self.assertEqual(result, [])

    def test_spawn_app_disables_python_bytecode_cache(self):
        sentinel = object()
        with (
            patch.dict("desktop_dev.os.environ", {"EXISTING": "1"}, clear=True),
            patch("desktop_dev.subprocess.Popen", return_value=sentinel) as popen,
        ):
            result = spawn_app()

        self.assertIs(result, sentinel)
        popen.assert_called_once()
        args, kwargs = popen.call_args
        self.assertEqual(args[0][1], "desktop_main.py")
        self.assertEqual(kwargs["cwd"], ROOT)
        self.assertEqual(kwargs["env"]["PYTHONDONTWRITEBYTECODE"], "1")
        self.assertEqual(kwargs["env"]["EXISTING"], "1")


if __name__ == "__main__":
    unittest.main()
