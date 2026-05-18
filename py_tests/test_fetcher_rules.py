import unittest

from desktop_py.core.fetcher_rules import (
    DEFAULT_FETCH_RULE_VERSION,
    DEFAULT_NOTIFICATION_RULES,
    DEFAULT_REFUND_RULES,
    DEFAULT_TRANSACTION_COMPLAINT_RULES,
    deadline_field_score,
    match_notification_title,
)
from desktop_py.core.fetcher_support import _fallback_from_responses


class FetcherRulesTestCase(unittest.TestCase):
    def test_default_rules_expose_stable_version(self):
        self.assertEqual(DEFAULT_REFUND_RULES.version, DEFAULT_FETCH_RULE_VERSION)
        self.assertEqual(DEFAULT_NOTIFICATION_RULES.version, DEFAULT_FETCH_RULE_VERSION)
        self.assertEqual(DEFAULT_TRANSACTION_COMPLAINT_RULES.version, DEFAULT_FETCH_RULE_VERSION)

    def test_transaction_complaint_rules_keep_current_contract(self):
        self.assertEqual(DEFAULT_TRANSACTION_COMPLAINT_RULES.target_account_names, ("当代情诗摘抄合集", "经典诗词摘抄"))
        self.assertEqual(DEFAULT_TRANSACTION_COMPLAINT_RULES.pending_status, 201)
        self.assertEqual(DEFAULT_TRANSACTION_COMPLAINT_RULES.pending_status_text, "待处理")
        self.assertEqual(DEFAULT_TRANSACTION_COMPLAINT_RULES.page_size, 50)

    def test_deadline_field_priority_prefers_appeal_deadline(self):
        self.assertGreater(
            deadline_field_score("$.data.user_refund_check_list[0].ctrl_info.appeal_deadline_time"),
            deadline_field_score("$.data.user_refund_check_list[0].ctrl_info.deadline_time"),
        )

        deadline = _fallback_from_responses(
            [
                {
                    "data": {
                        "user_refund_check_list": [
                            {
                                "ctrl_info": {
                                    "deadline_time": "1776147849",
                                    "appeal_deadline_time": "1776737974",
                                }
                            }
                        ]
                    }
                }
            ]
        )

        self.assertEqual(deadline, "2026-04-21 10:19:34")

    def test_deadline_field_priority_falls_back_when_preferred_field_missing(self):
        deadline = _fallback_from_responses(
            [
                {
                    "data": {
                        "user_refund_check_list": [
                            {
                                "ctrl_info": {
                                    "deadline_time": "1776147849",
                                }
                            }
                        ]
                    }
                }
            ]
        )

        self.assertEqual(deadline, "2026-04-14 14:24:09")

    def test_notification_rule_match_returns_rule_version(self):
        match = match_notification_title("小程序微信认证年审通知")

        self.assertTrue(match.matched)
        self.assertEqual(match.rule_name, "annual_review")
        self.assertEqual(match.rule_version, DEFAULT_FETCH_RULE_VERSION)


if __name__ == "__main__":
    unittest.main()
