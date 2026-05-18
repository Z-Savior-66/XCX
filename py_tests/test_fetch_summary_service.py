import unittest
from unittest.mock import Mock

from desktop_py.core.fetch_summary_service import (
    resend_pending_notifications,
    send_summary_with_pending_notification,
)
from desktop_py.core.models import FetchResult, PendingNotification


class FetchSummaryServiceTestCase(unittest.TestCase):
    def test_send_summary_with_pending_notification_queues_pending_item_on_failure(self):
        results = [FetchResult(account_name="账号A", ok=True, deadline_text="2026-04-20 09:00:00")]
        append_pending_notification_fn = Mock()

        with self.assertRaisesRegex(RuntimeError, "发送失败"):
            send_summary_with_pending_notification(
                "https://example.com/hook",
                results,
                build_summary_fn=lambda items: f"summary:{len(items)}",
                send_feishu_text_fn=lambda _webhook, _content: (_ for _ in ()).throw(RuntimeError("发送失败")),
                build_pending_notification_fn=lambda content, source="飞书汇总": PendingNotification(
                    id="abc123",
                    content=content,
                    created_at="2026-05-18 19:20:00",
                    source=source,
                ),
                append_pending_notification_fn=append_pending_notification_fn,
                pending_source="测试来源",
            )

        append_pending_notification_fn.assert_called_once()
        pending_notification = append_pending_notification_fn.call_args.args[0]
        self.assertEqual(pending_notification.content, "summary:1")
        self.assertEqual(pending_notification.source, "测试来源")

    def test_send_summary_with_pending_notification_returns_summary_on_success(self):
        results = [FetchResult(account_name="账号A", ok=True, deadline_text="2026-04-20 09:00:00")]
        append_pending_notification_fn = Mock()
        captured = {}

        summary = send_summary_with_pending_notification(
            "https://example.com/hook",
            results,
            build_summary_fn=lambda items: f"summary:{len(items)}",
            send_feishu_text_fn=lambda webhook, content: captured.update({"webhook": webhook, "content": content}),
            build_pending_notification_fn=lambda content, source="飞书汇总": PendingNotification(
                id="abc123",
                content=content,
                created_at="2026-05-18 19:20:00",
                source=source,
            ),
            append_pending_notification_fn=append_pending_notification_fn,
        )

        self.assertEqual(summary, "summary:1")
        self.assertEqual(captured["webhook"], "https://example.com/hook")
        self.assertEqual(captured["content"], "summary:1")
        append_pending_notification_fn.assert_not_called()

    def test_resend_pending_notifications_removes_each_item_after_success(self):
        notifications = [
            PendingNotification(id="a1", content="内容1", created_at="2026-05-18 19:20:00"),
            PendingNotification(id="b2", content="内容2", created_at="2026-05-18 19:20:01"),
        ]
        removed_ids: list[str] = []
        sent_payloads: list[tuple[str, str]] = []

        sent_count = resend_pending_notifications(
            "https://example.com/hook",
            notifications,
            send_feishu_text_fn=lambda webhook, content: sent_payloads.append((webhook, content)),
            remove_pending_notifications_fn=lambda ids: removed_ids.extend(ids),
        )

        self.assertEqual(sent_count, 2)
        self.assertEqual(sent_payloads, [("https://example.com/hook", "内容1"), ("https://example.com/hook", "内容2")])
        self.assertEqual(removed_ids, ["a1", "b2"])

    def test_resend_pending_notifications_returns_zero_for_empty_queue(self):
        removed_ids: list[str] = []

        sent_count = resend_pending_notifications(
            "https://example.com/hook",
            [],
            send_feishu_text_fn=lambda *_args: None,
            remove_pending_notifications_fn=lambda ids: removed_ids.extend(ids),
        )

        self.assertEqual(sent_count, 0)
        self.assertEqual(removed_ids, [])


if __name__ == "__main__":
    unittest.main()
