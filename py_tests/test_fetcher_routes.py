from pathlib import Path

from desktop_py.core.fetcher_pipeline import _build_collection_routes, _build_feedback_route, _build_pipeline_context
from desktop_py.core.models import FetchResult
from py_tests.fetcher_test_support import FetcherTestBase


class FetcherRouteTestCase(FetcherTestBase):
    def test_build_collection_routes_returns_notification_then_transaction_complaint(self):
        routes = _build_collection_routes(
            lambda *_args, **_kwargs: {"ok": True}, lambda *_args, **_kwargs: {"ok": True}
        )

        self.assertEqual(
            [(route.name, route.step_label) for route in routes], [("通知中心", "通知中心"), ("交易投诉", "交易投诉")]
        )
        self.assertTrue(callable(routes[0].collect_fn))
        self.assertTrue(callable(routes[1].collect_fn))

    def test_build_feedback_route_includes_ios_fallback_when_available(self):
        route = _build_feedback_route(lambda url: f"primary:{url}", lambda url: f"ios:{url}")

        self.assertEqual(route.name, "退款反馈页")
        self.assertEqual(route.step_label, "退款反馈页")
        self.assertIsNotNone(route.fallback_route)
        self.assertEqual(route.build_feedback_url_fn("https://example.com"), "primary:https://example.com")
        self.assertEqual(route.fallback_route.build_feedback_url_fn("https://example.com"), "ios:https://example.com")

    def test_build_pipeline_context_wires_routes_and_shared_dependencies(self):
        context = _build_pipeline_context(
            account_output_dir_fn=lambda account_name: Path(f"C:/temp/{account_name}"),
            register_response_capture_fn=lambda page, capture_fn: ([], lambda: None),
            capture_response_payload_fn=lambda response: response,
            resolve_bootstrap_url_fn=lambda account, output_dir: account.home_url,
            wait_for_url_contains_fn=lambda *args, **kwargs: True,
            extract_current_account_name_fn=lambda page: "当前账号",
            should_switch_for_account_fn=lambda account, current_name: False,
            switch_to_account_fn=lambda *args, **kwargs: None,
            log_fn=lambda *_args: None,
            open_feedback_page_fn=lambda *args, **kwargs: "",
            build_feedback_url_fn=lambda url: f"primary:{url}",
            build_ios_refund_feedback_url_fn=lambda url: f"ios:{url}",
            wait_for_iframe_ready_fn=lambda *args, **kwargs: True,
            resolve_frame_locator_fn=lambda *args, **kwargs: object(),
            business_iframe_selector_fn=lambda page: "#js_iframe",
            safe_page_content_fn=lambda page: "<html></html>",
            fetch_notifications_fn=lambda *args, **kwargs: {"ok": True},
            fetch_transaction_complaints_fn=None,
            fetch_paginated_refund_list_captures_fn=None,
            is_empty_refund_list_fn=lambda text: False,
            confirm_empty_refund_list_fn=lambda **kwargs: (True, ""),
            build_empty_refund_result_fn=lambda **kwargs: FetchResult(account_name="账号A", ok=True),
            build_detail_result_fn=lambda **kwargs: FetchResult(account_name="账号A", ok=True),
        )

        self.assertEqual([route.name for route in context.collection_routes], ["通知中心"])
        self.assertEqual(context.feedback_route.name, "退款反馈页")
        self.assertEqual(context.feedback_route.fallback_route.name, "iOS退款问询")


if __name__ == "__main__":
    import unittest

    unittest.main()
