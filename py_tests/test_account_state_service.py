import unittest

from desktop_py.core.account_state_service import apply_batch_fetch_results, apply_fetch_result
from desktop_py.core.models import AccountConfig, FetchResult


class AccountStateServiceTestCase(unittest.TestCase):
    def test_apply_fetch_result_updates_account_state(self):
        account = AccountConfig(name="导入账号A", state_path="storage/shared.json", is_entry_account=False)
        result = FetchResult(
            account_name="导入账号A",
            ok=True,
            actual_account_name="实际账号A",
            deadline_text="2026-04-18 10:30:00",
            note="已完成详情页抓取。",
            page_url="https://example.com/detail",
        )

        current_main_account_name = apply_fetch_result(account, result)

        self.assertEqual(current_main_account_name, "实际账号A")
        self.assertEqual(account.last_status, "抓取成功")
        self.assertEqual(account.last_note, "已完成详情页抓取。；当前实际账号：实际账号A")
        self.assertEqual(account.feedback_url, "https://example.com/detail")
        self.assertEqual(account.session_status, "valid")

    def test_apply_batch_fetch_results_returns_latest_actual_account_name(self):
        accounts = [
            AccountConfig(name="导入账号A", state_path="storage/shared.json", is_entry_account=False),
            AccountConfig(name="导入账号B", state_path="storage/shared.json", is_entry_account=False),
        ]
        results = [
            FetchResult(
                account_name="导入账号A", ok=True, actual_account_name="账号甲", page_url="https://example.com/a"
            ),
            FetchResult(
                account_name="导入账号B", ok=True, actual_account_name="账号乙", page_url="https://example.com/b"
            ),
        ]

        latest_actual_account_name = apply_batch_fetch_results(accounts, results)

        self.assertEqual(latest_actual_account_name, "账号乙")
        self.assertEqual(accounts[0].feedback_url, "https://example.com/a")
        self.assertEqual(accounts[1].feedback_url, "https://example.com/b")


if __name__ == "__main__":
    unittest.main()
