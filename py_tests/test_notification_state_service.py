import unittest

from desktop_py.core.models import AccountConfig
from desktop_py.core.notification_state_service import actual_account_name_from_note, clear_pushed_fetch_state


class NotificationStateServiceTestCase(unittest.TestCase):
    def test_clear_pushed_fetch_state_only_clears_successful_imported_accounts(self):
        accounts = [
            AccountConfig(
                name="主账号",
                state_path="storage/shared.json",
                is_entry_account=True,
                enabled=True,
                last_status="抓取成功",
                last_deadline="2026-04-20 11:42:31",
                last_note="主账号状态。",
            ),
            AccountConfig(
                name="导入账号A",
                state_path="storage/shared.json",
                is_entry_account=False,
                enabled=True,
                last_status="抓取成功",
                last_deadline="2026-04-20 11:42:31",
                last_note="已完成详情页抓取。",
            ),
            AccountConfig(
                name="导入账号B",
                state_path="storage/shared.json",
                is_entry_account=False,
                enabled=False,
                last_status="抓取成功",
                last_deadline="2026-04-21 11:42:31",
                last_note="已完成详情页抓取。",
            ),
            AccountConfig(
                name="导入账号C",
                state_path="storage/shared.json",
                is_entry_account=False,
                enabled=True,
                last_status="抓取失败",
                last_deadline="",
                last_note="页面未出现业务 iframe",
            ),
        ]

        cleared = clear_pushed_fetch_state(accounts)

        self.assertEqual(cleared, 1)
        self.assertEqual(accounts[1].last_deadline, "")
        self.assertEqual(accounts[1].last_status, "")
        self.assertEqual(accounts[1].last_note, "")
        self.assertEqual(accounts[2].last_status, "抓取成功")
        self.assertEqual(accounts[3].last_status, "抓取失败")

    def test_actual_account_name_from_note_extracts_prefix(self):
        self.assertEqual(
            actual_account_name_from_note(
                "已完成详情页抓取。；当前实际账号：实际账号A", actual_account_prefix="当前实际账号："
            ),
            "实际账号A",
        )


if __name__ == "__main__":
    unittest.main()
