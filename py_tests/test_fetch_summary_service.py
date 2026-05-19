import unittest

from desktop_py.core.fetch_summary_service import (
    send_summary,
)
from desktop_py.core.models import FetchResult


class FetchSummaryServiceTestCase(unittest.TestCase):
    def test_send_summary_raises_on_send_failure(self):
        results = [FetchResult(account_name="账号A", ok=True, deadline_text="2026-04-20 09:00:00")]

        with self.assertRaisesRegex(RuntimeError, "发送失败"):
            send_summary(
                "https://example.com/hook",
                results,
                build_summary_fn=lambda items: f"summary:{len(items)}",
                send_feishu_text_fn=lambda _webhook, _content: (_ for _ in ()).throw(RuntimeError("发送失败")),
            )

    def test_send_summary_returns_summary_on_success(self):
        results = [FetchResult(account_name="账号A", ok=True, deadline_text="2026-04-20 09:00:00")]
        captured = {}

        summary = send_summary(
            "https://example.com/hook",
            results,
            build_summary_fn=lambda items: f"summary:{len(items)}",
            send_feishu_text_fn=lambda webhook, content: captured.update({"webhook": webhook, "content": content}),
        )

        self.assertEqual(summary, "summary:1")
        self.assertEqual(captured["webhook"], "https://example.com/hook")
        self.assertEqual(captured["content"], "summary:1")

if __name__ == "__main__":
    unittest.main()
