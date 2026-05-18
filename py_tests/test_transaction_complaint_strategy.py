from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from desktop_py.core.fetcher_rules import TransactionComplaintRuleSet
from desktop_py.core.fetcher_support import FetchError, FetchErrorCode
from desktop_py.core.transaction_complaint_strategy import (
    PENDING_TRANSACTION_COMPLAINT_STATUS,
    build_transaction_complaint_list_url,
    build_transaction_complaint_summary,
    fetch_pending_transaction_complaint_items,
    fetch_transaction_complaints,
    request_transaction_complaint_json,
    should_fetch_transaction_complaints,
)
from py_tests.fetcher_test_support import AccountConfig, FetcherTestBase


class FakeComplaintPage:
    def __init__(self, url: str = "https://mp.weixin.qq.com/wxamp/index/index?token=1"):
        self.url = url
        self.goto_calls: list[str] = []
        self.load_state_calls: list[tuple[str, int]] = []

    def goto(self, url, wait_until=None, timeout=None):
        self.goto_calls.append(url)
        self.url = url

    def wait_for_load_state(self, state=None, timeout=None):
        self.load_state_calls.append((state, timeout or 0))

    def wait_for_timeout(self, timeout):
        return None

    def content(self):
        return "<html>交易投诉</html>"

    def locator(self, selector, **kwargs):
        return type("Locator", (), {"count": lambda self: 0})()


class TransactionComplaintStrategyTestCase(FetcherTestBase):
    def test_target_account_whitelist_only_enables_two_accounts(self):
        self.assertTrue(
            should_fetch_transaction_complaints(
                AccountConfig(name="当代情诗摘抄合集", state_path="storage/shared.json", is_entry_account=False)
            )
        )
        self.assertTrue(
            should_fetch_transaction_complaints(
                AccountConfig(name="经典诗词摘抄", state_path="storage/shared.json", is_entry_account=False)
            )
        )
        self.assertFalse(
            should_fetch_transaction_complaints(
                AccountConfig(name="其它账号", state_path="storage/shared.json", is_entry_account=False)
            )
        )

    def test_fetch_pending_transaction_complaint_items_requests_pending_status_and_normalizes_items(self):
        requested_urls: list[str] = []

        def request_json(_page, url):
            requested_urls.append(url)
            return {
                "ret": 0,
                "countAll": 2,
                "complaintOrderList": [
                    {
                        "complaintOrderId": "48383455",
                        "status": PENDING_TRANSACTION_COMPLAINT_STATUS,
                        "createTime": 1778993208,
                        "expireTime": 1779257741,
                        "orderId": "payorder@1",
                        "phoneNumber": "13800000000",
                        "nickName": "用户A",
                    },
                    {"complaintOrderId": "48383456", "status": 204},
                ],
            }

        items = fetch_pending_transaction_complaint_items(object(), "token-1", request_json_fn=request_json)

        query = parse_qs(urlparse(requested_urls[0]).query)
        self.assertEqual(query["status"], [str(PENDING_TRANSACTION_COMPLAINT_STATUS)])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["complaint_order_id"], "48383455")
        self.assertEqual(items[0]["status_text"], "待处理")
        self.assertEqual(items[0]["create_time"], "2026-05-17 12:46:48")

    def test_fetch_pending_transaction_complaint_items_fetches_remaining_pages(self):
        requested_pages: list[str] = []

        def request_json(_page, url):
            page = parse_qs(urlparse(url).query)["page"][0]
            requested_pages.append(page)
            return {
                "ret": 0,
                "countAll": 51,
                "complaintOrderList": [
                    {
                        "complaintOrderId": f"单号{page}",
                        "status": PENDING_TRANSACTION_COMPLAINT_STATUS,
                    }
                ],
            }

        items = fetch_pending_transaction_complaint_items(object(), "token-1", request_json_fn=request_json)

        self.assertEqual(requested_pages, ["1", "2"])
        self.assertEqual([item["complaint_order_id"] for item in items], ["单号1", "单号2"])

    def test_fetch_pending_transaction_complaint_items_uses_rule_object(self):
        requested_queries: list[dict[str, list[str]]] = []
        rules = TransactionComplaintRuleSet(
            version="test",
            target_account_names=("自定义账号",),
            pending_status=299,
            pending_status_text="自定义待处理",
            page_size=2,
        )

        def request_json(_page, url):
            query = parse_qs(urlparse(url).query)
            requested_queries.append(query)
            page = query["page"][0]
            return {
                "ret": 0,
                "countAll": 3,
                "complaintOrderList": [
                    {
                        "complaintOrderId": f"自定义单号{page}",
                        "status": 299,
                    }
                ],
            }

        items = fetch_pending_transaction_complaint_items(
            object(), "token-1", request_json_fn=request_json, rules=rules
        )

        self.assertEqual([query["page"] for query in requested_queries], [["1"], ["2"]])
        self.assertEqual([query["pageSize"] for query in requested_queries], [["2"], ["2"]])
        self.assertEqual([query["status"] for query in requested_queries], [["299"], ["299"]])
        self.assertEqual([item["status_text"] for item in items], ["自定义待处理", "自定义待处理"])

    def test_fetch_transaction_complaints_skips_non_target_account(self):
        page = FakeComplaintPage()
        account = AccountConfig(name="其它账号", state_path="storage/shared.json", is_entry_account=False)

        outcome = fetch_transaction_complaints(
            page,
            account=account,
            logger=None,
            output_dir=type("Path", (), {})(),
            log_fn=lambda *_args: None,
            wait_for_url_contains_fn=lambda *_args, **_kwargs: True,
            safe_page_content_fn=lambda current_page: current_page.content(),
            request_json_fn=lambda *_args: (_ for _ in ()).throw(AssertionError("不应请求接口")),
        )

        self.assertTrue(outcome["ok"])
        self.assertFalse(outcome["enabled"])
        self.assertEqual(outcome["summary"], "")

    def test_fetch_transaction_complaints_returns_summary_and_persists_target_result(self):
        page = FakeComplaintPage()
        account = AccountConfig(name="经典诗词摘抄", state_path="storage/shared.json", is_entry_account=False)
        written: dict[str, object] = {}

        def request_json(_page, url):
            self.assertIn("status=201", url)
            return {
                "ret": 0,
                "countAll": 1,
                "complaintOrderList": [{"complaintOrderId": "48383455", "status": 201}],
            }

        with patch("desktop_py.core.transaction_complaint_strategy.write_account_output_json") as write_json:
            write_json.side_effect = lambda account_name, filename, payload: written.update(
                {"account_name": account_name, "filename": filename, "payload": payload}
            )
            outcome = fetch_transaction_complaints(
                page,
                account=account,
                logger=None,
                output_dir=type("Path", (), {})(),
                log_fn=lambda *_args: None,
                wait_for_url_contains_fn=lambda *_args, **_kwargs: True,
                safe_page_content_fn=lambda current_page: current_page.content(),
                request_json_fn=request_json,
            )

        self.assertTrue(outcome["ok"])
        self.assertTrue(outcome["enabled"])
        self.assertEqual(outcome["summary"], "交易投诉待处理 1 条：48383455")
        self.assertEqual(written["filename"], "transaction_complaints.json")
        self.assertEqual(written["payload"][0]["status_text"], "待处理")

    def test_fetch_transaction_complaints_records_failure_as_non_blocking_outcome(self):
        page = FakeComplaintPage()
        account = AccountConfig(name="经典诗词摘抄", state_path="storage/shared.json", is_entry_account=False)

        with (
            patch("desktop_py.core.transaction_complaint_strategy.write_account_output_json") as write_json,
            patch("desktop_py.core.transaction_complaint_strategy.write_account_output_text") as write_text,
        ):
            outcome = fetch_transaction_complaints(
                page,
                account=account,
                logger=None,
                output_dir=type("Path", (), {})(),
                log_fn=lambda *_args: None,
                wait_for_url_contains_fn=lambda *_args, **_kwargs: True,
                safe_page_content_fn=lambda current_page: current_page.content(),
                request_json_fn=lambda *_args: {"ret": 1, "errmsg": "接口失败"},
            )

        self.assertFalse(outcome["ok"])
        self.assertIn("交易投诉抓取失败", outcome["summary"])
        self.assertEqual(outcome["error_code"], "transaction_complaint_api_failed")
        write_json.assert_called_with("经典诗词摘抄", "transaction_complaints.json", [])
        write_text.assert_called()

    def test_request_transaction_complaint_json_invalid_payload_has_error_code(self):
        class InvalidPayloadPage:
            def evaluate(self, _script, _request_url):
                return "not-json-object"

        with self.assertRaises(FetchError) as raised:
            request_transaction_complaint_json(InvalidPayloadPage(), "https://example.com/api")

        self.assertEqual(raised.exception.code, FetchErrorCode.TRANSACTION_COMPLAINT_RESPONSE_INVALID)
        self.assertEqual(raised.exception.evidence[0]["metadata"]["payload_type"], "str")

    def test_build_transaction_complaint_summary_handles_empty_and_multiple_items(self):
        self.assertEqual(build_transaction_complaint_summary([]), "交易投诉无待处理投诉。")
        summary = build_transaction_complaint_summary(
            [
                {"complaint_order_id": "1"},
                {"complaint_order_id": "2"},
                {"complaint_order_id": "3"},
                {"complaint_order_id": "4"},
            ]
        )
        self.assertEqual(summary, "交易投诉待处理 4 条：1、2、3 等")

    def test_build_transaction_complaint_list_url_uses_expected_contract(self):
        query = parse_qs(urlparse(build_transaction_complaint_list_url("token-1", page=3)).query)

        self.assertEqual(query["token"], ["token-1"])
        self.assertEqual(query["page"], ["3"])
        self.assertEqual(query["pageSize"], ["50"])
        self.assertEqual(query["status"], ["201"])
