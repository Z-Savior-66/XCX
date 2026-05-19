from pathlib import Path

from desktop_py.core.fetcher_pipeline import (
    _build_collection_routes,
    _build_feedback_routes,
    _build_pipeline_context,
    _collect_ios_refund_subject_captures,
)
from desktop_py.core.models import FetchResult
from py_tests.fetcher_test_support import FetcherTestBase


class _FakeIosButton:
    def __init__(self, text: str, click_cb=None):
        self._text = text
        self._click_cb = click_cb

    def evaluate(self, _script):
        return bool(self._text)

    def click(self, timeout=None):
        if self._click_cb is not None:
            self._click_cb()


class _FakeIosButtonGroup:
    def __init__(self, frame):
        self._frame = frame

    def count(self):
        return 1

    def nth(self, index):
        return _FakeIosButton("搜索", click_cb=self._frame.trigger_search)


class _FakeIosOption:
    def __init__(self, frame, index: int):
        self._frame = frame
        self._index = index

    def click(self, timeout=None):
        self._frame.selected_index = self._index


class _FakeIosOptionGroup:
    def __init__(self, frame):
        self._frame = frame

    def nth(self, index):
        return _FakeIosOption(self._frame, index)


class _FakeIosFrame:
    def __init__(self, captures):
        self.name = "js_iframe"
        self.url = "https://gamemp.weixin.qq.com/minigame/index.html#/old-teenager-refund-process/list"
        self._captures = captures
        self.options = ["主体A", "主体B"]
        self.selected_index = 0
        self.searches: list[str] = []

    def wait_for_selector(self, selector, timeout=None):
        return None

    def wait_for_timeout(self, timeout):
        return None

    def eval_on_selector_all(self, selector, _script):
        if selector == ".dropdown-switch-item":
            return [{"title": value, "text": value} for value in self.options]
        return []

    def eval_on_selector(self, selector, _script):
        if selector == ".drop-selected":
            return self.options[self.selected_index]
        raise AssertionError(selector)

    def locator(self, selector):
        if selector == ".dropdown_switch":
            return _FakeIosButton("")
        if selector == ".dropdown_data_item":
            return _FakeIosOptionGroup(self)
        if selector == "button":
            return _FakeIosButtonGroup(self)
        raise AssertionError(selector)

    def trigger_search(self):
        subject = self.options[self.selected_index]
        self.searches.append(subject)
        self._captures.append({"response_type": "list", "body": {"data": {"list": [{"subject": subject}]}}})


class _FakeIosPage:
    def __init__(self, frame):
        self.frames = [frame]


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

    def test_build_feedback_routes_returns_regular_then_ios_when_available(self):
        routes = _build_feedback_routes(lambda url: f"primary:{url}", lambda url: f"ios:{url}")

        self.assertEqual([route.name for route in routes], ["退款反馈页", "iOS退款问询"])
        self.assertEqual(routes[0].build_feedback_url_fn("https://example.com"), "primary:https://example.com")
        self.assertEqual(routes[1].build_feedback_url_fn("https://example.com"), "ios:https://example.com")

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
        self.assertEqual([route.name for route in context.feedback_routes], ["退款反馈页", "iOS退款问询"])

    def test_collect_ios_refund_subject_captures_switches_other_subjects_and_paginates(self):
        captures = [{"response_type": "list", "body": {"data": {"list": []}}}]
        frame = _FakeIosFrame(captures)
        page = _FakeIosPage(frame)
        pagination_calls: list[int] = []
        logs: list[str] = []

        def fetch_paginated(*, page, captures, logger, log_fn):
            pagination_calls.append(len(captures))
            return list(captures) + [{"page_capture": len(pagination_calls)}]

        result = _collect_ios_refund_subject_captures(
            page=page,
            captures=captures,
            logger=None,
            log_fn=lambda _logger, message: logs.append(message),
            wait_or_cancel_fn=lambda *_args, **_kwargs: None,
            fetch_paginated_refund_list_captures_fn=fetch_paginated,
            is_cancelled=None,
        )

        self.assertEqual(frame.searches, ["主体B"])
        self.assertEqual(pagination_calls, [1, 2])
        self.assertEqual(result[-1], {"page_capture": 2})


if __name__ == "__main__":
    import unittest

    unittest.main()
