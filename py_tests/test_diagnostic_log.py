import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from desktop_py.core.diagnostic_log import append_session_log, session_log_file


class DiagnosticLogTestCase(unittest.TestCase):
    def test_append_session_log_writes_daily_log_file(self):
        with TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir)
            now = datetime(2026, 5, 7, 10, 11, 12)

            path = append_session_log("账号 主账号 登录态掉线：页面显示登录超时", now=now, log_dir=log_dir)

            self.assertEqual(path, log_dir / "login-session-2026-05-07.log")
            self.assertIsNotNone(path)
            self.assertIn(
                "[2026-05-07 10:11:12] 账号 主账号 登录态掉线：页面显示登录超时",
                path.read_text(encoding="utf-8"),
            )

    def test_session_log_file_uses_daily_name(self):
        now = datetime(2026, 5, 8, 1, 2, 3)
        with TemporaryDirectory() as temp_dir:
            path = session_log_file(now=now, log_dir=Path(temp_dir))

        self.assertEqual(path.name, "login-session-2026-05-08.log")

    def test_append_session_log_keeps_branch_and_page_url_in_message(self):
        with TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir)
            now = datetime(2026, 5, 8, 9, 30, 0)

            path = append_session_log(
                "账号 主账号 登录态续期失败：未检测到后台账号信息；判定分支=missing_backend_account_signals；page.url=https://mp.weixin.qq.com/",
                now=now,
                log_dir=log_dir,
            )

            self.assertIsNotNone(path)
            self.assertIn(
                "判定分支=missing_backend_account_signals；page.url=https://mp.weixin.qq.com/",
                path.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
