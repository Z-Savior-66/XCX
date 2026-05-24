import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from desktop_py.core.fetcher_rules import DEFAULT_TRANSACTION_COMPLAINT_RULES, load_transaction_complaint_rules


class TransactionComplaintRulesTestCase(unittest.TestCase):
    def test_load_transaction_complaint_rules_returns_default_when_file_missing(self):
        missing_path = Path(tempfile.gettempdir()) / "nonexistent_transaction_complaint_rules.json"
        if missing_path.exists():
            missing_path.unlink()

        rules = load_transaction_complaint_rules(missing_path)

        self.assertEqual(rules, DEFAULT_TRANSACTION_COMPLAINT_RULES)

    def test_load_transaction_complaint_rules_accepts_empty_target_list(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "transaction_complaint_rules.json"
            path.write_text(
                json.dumps(
                    {
                        "version": "test",
                        "target_account_names": [],
                        "pending_status": 299,
                        "pending_status_text": "自定义待处理",
                        "page_size": 2,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            rules = load_transaction_complaint_rules(path)

        self.assertEqual(rules.target_account_names, ())
        self.assertEqual(rules.pending_status, 299)
        self.assertEqual(rules.pending_status_text, "自定义待处理")
        self.assertEqual(rules.page_size, 2)

    def test_load_transaction_complaint_rules_prefers_data_dir_file(self):
        from desktop_py.core import fetcher_rules

        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            data_dir.mkdir()
            data_path = data_dir / "transaction_complaint_rules.json"
            data_path.write_text(
                json.dumps(
                    {
                        "version": "data",
                        "target_account_names": ["安装包账号"],
                        "pending_status": 303,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch.object(fetcher_rules, "DATA_DIR", data_dir):
                rules = fetcher_rules.load_transaction_complaint_rules()

        self.assertEqual(rules.version, "data")
        self.assertEqual(rules.target_account_names, ("安装包账号",))
        self.assertEqual(rules.pending_status, 303)

    def test_load_transaction_complaint_rules_supports_multiple_accounts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "transaction_complaint_rules.json"
            path.write_text(
                json.dumps(
                    {
                        "target_account_names": ["账号A", "账号B", "账号C"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            rules = load_transaction_complaint_rules(path)

        self.assertEqual(rules.target_account_names, ("账号A", "账号B", "账号C"))


if __name__ == "__main__":
    unittest.main()
