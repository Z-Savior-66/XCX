import unittest
from unittest.mock import patch

from desktop_py.core.fetcher_diagnostics import (
    build_success_log_lines,
    compose_fetch_result,
    select_final_refund_outcome,
    write_batch_diagnostic_index_safely,
    write_fetch_result_payload,
)
from desktop_py.core.fetcher_manifest import BatchDiagnosticAccountRecord, BatchDiagnosticIndex
from desktop_py.core.fetcher_routes import FeedbackRoute
from desktop_py.core.models import FetchResult


class FetcherDiagnosticsTestCase(unittest.TestCase):
    def test_select_final_refund_outcome_prefers_earliest_deadline(self):
        first = type(
            "Outcome",
            (),
            {"result": FetchResult(account_name="账号A", ok=True, deadline_text="2026-05-20 10:00:00")},
        )()
        second = type(
            "Outcome",
            (),
            {"result": FetchResult(account_name="账号A", ok=True, deadline_text="2026-05-21 10:00:00")},
        )()

        chosen = select_final_refund_outcome((second, first))

        self.assertIs(chosen, first)

    def test_select_final_refund_outcome_rejects_empty_outcomes(self):
        with self.assertRaisesRegex(ValueError, "退款结果列表不能为空"):
            select_final_refund_outcome(())

    def test_build_success_log_lines_includes_transaction_complaint_summary(self):
        lines = build_success_log_lines(
            notification_outcome={
                "ok": True,
                "notifications": [],
                "summary": "通知中心无目标未读消息。",
                "page_url": "https://example.com/notice",
            },
            transaction_complaint_outcome={
                "ok": True,
                "enabled": True,
                "complaints": [{"complaint_order_id": "48383455"}],
                "summary": "交易投诉待处理 1 条：48383455",
                "page_url": "https://example.com/complaint",
            },
            refund_outcomes=(),
        )

        self.assertEqual(
            lines,
            [
                "交易投诉待处理 1 条，投诉编号：48383455。",
                "通知中心无目标未读消息。",
            ],
        )

    def test_build_success_log_lines_includes_empty_transaction_complaint_summary(self):
        lines = build_success_log_lines(
            notification_outcome={
                "ok": True,
                "notifications": [],
                "summary": "通知中心无目标未读消息。",
                "page_url": "https://example.com/notice",
            },
            transaction_complaint_outcome={
                "ok": True,
                "enabled": True,
                "complaints": [],
                "summary": "交易投诉无待处理投诉。",
                "page_url": "https://example.com/complaint",
            },
            refund_outcomes=(),
        )

        self.assertEqual(
            lines,
            [
                "交易投诉无待处理。",
                "通知中心无目标未读消息。",
            ],
        )

    def test_build_success_log_lines_orders_refund_ios_before_notification(self):
        refund = type(
            "Outcome",
            (),
            {
                "route": FeedbackRoute(name="regular", step_label="退款反馈页", build_feedback_url_fn=lambda url: url),
                "result": FetchResult(account_name="小章鱼消消乐", ok=True, deadline_text="2026-05-29 11:20:47"),
            },
        )()
        ios_refund = type(
            "Outcome",
            (),
            {
                "route": FeedbackRoute(name="ios", step_label="iOS退款问询", build_feedback_url_fn=lambda url: url),
                "result": FetchResult(account_name="小章鱼消消乐", ok=True, deadline_text=""),
            },
        )()

        lines = build_success_log_lines(
            notification_outcome={
                "ok": True,
                "notifications": [],
                "summary": "通知中心无目标未读消息。",
                "page_url": "https://example.com/notice",
            },
            refund_outcomes=(refund, ios_refund),
        )

        self.assertEqual(
            lines,
            [
                "未成年退款申请处理截止时间：2026-05-29 11:20:47。",
                "IOS退款问询当前无待处理申请。",
                "通知中心无目标未读消息。",
            ],
        )

    def test_compose_fetch_result_merges_notification_and_transaction_notes(self):
        result, result_extra = compose_fetch_result(
            page=object(),
            account_name="账号A",
            refund_outcomes=(
                type(
                    "Outcome",
                    (),
                    {"result": FetchResult(account_name="账号A", ok=True, deadline_text="2026-05-20 10:00:00")},
                )(),
            ),
            notification_outcome={"ok": True, "notifications": [{"id": 1}], "summary": "通知中心命中"},
            transaction_complaint_outcome={
                "enabled": True,
                "ok": True,
                "complaints": [{"id": 2}],
                "summary": "交易投诉命中",
                "page_url": "https://example.com/complaints",
            },
            set_page_current_account_name_fn=lambda _page, _name: None,
        )

        self.assertEqual(result.account_name, "账号A")
        self.assertIn("通知中心命中", result.note)
        self.assertIn("交易投诉命中", result.note)
        self.assertEqual(result_extra["notifications"], [{"id": 1}])
        self.assertEqual(result_extra["transaction_complaints"], [{"id": 2}])

    def test_compose_fetch_result_orders_transaction_note_before_notification_note(self):
        result, result_extra = compose_fetch_result(
            page=object(),
            account_name="当代情诗摘抄合集",
            refund_outcomes=(),
            notification_outcome={
                "ok": True,
                "notifications": [{"title": "你的账号收到一条侵权投诉"}],
                "summary": "通知中心未读消息 1 条：你的账号收到一条侵权投诉",
            },
            transaction_complaint_outcome={
                "enabled": True,
                "ok": True,
                "complaints": [{"complaint_order_id": "48648037"}],
                "summary": "交易投诉待处理 1 条：48648037",
                "page_url": "https://example.com/complaints",
            },
            set_page_current_account_name_fn=lambda _page, _name: None,
        )

        self.assertLess(result.note.index("交易投诉待处理"), result.note.index("通知中心未读消息"))
        self.assertEqual(result_extra["notifications"], [{"title": "你的账号收到一条侵权投诉"}])
        self.assertEqual(result_extra["transaction_complaints"], [{"complaint_order_id": "48648037"}])

    def test_write_helpers_delegate_and_log_failure(self):
        with patch("desktop_py.core.fetcher_diagnostics.write_fetch_result") as mock_write_result:
            write_fetch_result_payload(
                "账号A",
                FetchResult(account_name="账号A", ok=True),
                result_extra={"notifications": []},
                notification_outcome={"ok": True},
            )

        mock_write_result.assert_called_once()

        index = BatchDiagnosticIndex(run_id="run-1", started_at="2026-05-19 16:00:00", total_accounts=1)
        index.accounts.append(
            BatchDiagnosticAccountRecord(account_name="账号A", status="ok", ok=True, manifest_path="m", result_path="r")
        )

        messages: list[str] = []
        with patch(
            "desktop_py.core.fetcher_diagnostics.write_batch_diagnostic_index",
            side_effect=RuntimeError("boom"),
        ):
            write_batch_diagnostic_index_safely(index, messages.append)

        self.assertEqual(messages, ["写入批量诊断索引失败：boom"])
