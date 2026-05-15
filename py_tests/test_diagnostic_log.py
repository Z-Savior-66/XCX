import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from desktop_py.core.diagnostic_log import (
    append_session_log,
    log_session_offline,
    log_session_renew_failed,
    session_log_file,
)


class DiagnosticLogTestCase(unittest.TestCase):
    def test_session_log_file_uses_daily_login_session_name(self):
        with TemporaryDirectory() as temp_dir:
            path = session_log_file(now=datetime(2026, 5, 15, 8, 0, 0), log_dir=Path(temp_dir))

        self.assertTrue(str(path).endswith("login-session-2026-05-15.log"))

    def test_append_session_log_writes_timestamped_line(self):
        with TemporaryDirectory() as temp_dir:
            path = append_session_log("登录态异常", now=datetime(2026, 5, 15, 8, 1, 2), log_dir=Path(temp_dir))
            assert path is not None
            content = path.read_text(encoding="utf-8")

        self.assertIn("[2026-05-15 08:01:02] 登录态异常", content)

    def test_session_failure_logs_include_branch_and_page_url(self):
        with TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir)
            offline_path = log_session_offline(
                "主账号",
                "未检测到后台账号信息",
                branch="missing_backend_account_signals",
                page_url="https://mp.weixin.qq.com/",
                log_dir=log_dir,
            )
            assert offline_path is not None

            renew_path = log_session_renew_failed(
                "主账号",
                "保存后复验失败",
                branch="saved_state_verify_failed",
                page_url="https://mp.weixin.qq.com/wxamp/index/index?token=1",
                log_dir=log_dir,
            )
            assert renew_path is not None
            content = renew_path.read_text(encoding="utf-8")

        self.assertIn("账号 主账号 登录态掉线：未检测到后台账号信息", content)
        self.assertIn("账号 主账号 登录态续期失败：保存后复验失败", content)
        self.assertIn("判定分支=missing_backend_account_signals", content)
        self.assertIn("判定分支=saved_state_verify_failed", content)
        self.assertIn("page.url=https://mp.weixin.qq.com/wxamp/index/index?token=1", content)


if __name__ == "__main__":
    unittest.main()
