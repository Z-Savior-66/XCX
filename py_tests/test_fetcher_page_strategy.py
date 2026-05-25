from unittest.mock import patch

from py_tests.fetcher_test_support import (
    AccountConfig,
    FakeFrame,
    FakeLocator,
    FakePage,
    FakeResponse,
    FetcherTestBase,
    Path,
    TemporaryDirectory,
    _fallback_from_responses,
    business_iframe_selector,
    classify_refund_response_type,
    extract_labeled_datetime,
    is_login_timeout_page,
    is_wechat_mp_root_page_url,
    recover_login_timeout_page,
    recover_wechat_mp_root_page,
    safe_page_content,
    wait_for_iframe_ready,
)


class FetcherPageStrategyTestCase(FetcherTestBase):
    def test_business_iframe_selector_prefers_js_iframe(self):
        page = FakePage(
            locator_map={
                ("#js_iframe", None): FakeLocator(count=1),
                ("iframe[src*='gameFeedback']", None): FakeLocator(count=1),
            }
        )

        self.assertEqual(business_iframe_selector(page), "#js_iframe")

    def test_business_iframe_selector_falls_back_to_game_feedback_iframe(self):
        page = FakePage(
            locator_map={
                ("#js_iframe", None): FakeLocator(count=0),
                ("iframe[src*='gameFeedback']", None): FakeLocator(count=1),
            }
        )

        self.assertEqual(business_iframe_selector(page), "iframe[src*='gameFeedback']")

    def test_business_iframe_selector_ignores_generic_non_business_iframe(self):
        page = FakePage(
            locator_map={
                ("#js_iframe", None): FakeLocator(count=0),
                ("iframe[src*='gameFeedback']", None): FakeLocator(count=0),
                ("iframe[src*='refund']", None): FakeLocator(count=0),
                ("iframe", None): FakeLocator(count=1),
            }
        )

        self.assertEqual(business_iframe_selector(page), "")

    def test_wait_for_iframe_ready_accepts_fallback_iframe_with_refund_text(self):
        frame = FakeFrame(text="退款申请 处理截止时间：2026-04-20 18:00")
        page = FakePage(
            locator_map={
                ("#js_iframe", None): FakeLocator(count=0),
                ("iframe[src*='gameFeedback']", None): FakeLocator(count=1, frame=frame),
            }
        )

        self.assertTrue(wait_for_iframe_ready(page, timeout_ms=1000))
        self.assertIn(("domcontentloaded", 1000), frame.load_state_calls)

    def test_offline_fixture_extracts_deadline_from_page_text(self):
        text = "退款申请详情 处理截止时间：2026-04-20 18:00 请尽快处理"

        deadline = extract_labeled_datetime(text, "处理截止时间")

        self.assertEqual(deadline, "2026-04-20 18:00")

    def test_safe_page_content_retries_until_success(self):
        page = FakePage()
        page.set_content_results([RuntimeError("navigating"), "<html>ok</html>"])

        content = safe_page_content(page, timeout_ms=1000)

        self.assertEqual(content, "<html>ok</html>")
        self.assertGreaterEqual(len(page.wait_calls), 1)

    def test_safe_page_content_waits_for_navigation_to_settle(self):
        page = FakePage()
        page.set_content_results(
            [
                RuntimeError(
                    "Page.content: Unable to retrieve content because the page is navigating and changing the content."
                ),
                "<html>ok</html>",
            ]
        )

        content = safe_page_content(page, timeout_ms=1500)

        self.assertEqual(content, "<html>ok</html>")
        self.assertIn(("domcontentloaded", 1000), page.load_state_calls)
        self.assertIn(("networkidle", 1000), page.load_state_calls)

    def test_is_login_timeout_page_detects_recoverable_timeout_screen(self):
        class TimeoutPage:
            def __init__(self):
                self.url = "https://mp.weixin.qq.com/"

            def wait_for_load_state(self, state=None, timeout=None):
                return None

            def locator(self, selector, **kwargs):
                if selector == "text=登录超时，请重新登录":
                    return FakeLocator(count=1)
                if selector == "text=小程序":
                    return FakeLocator(count=1)
                if selector == "text=退出登录":
                    return FakeLocator(count=1)
                return FakeLocator()

            def content(self):
                return "<div>登录超时，请重新登录</div><div>小程序</div><div>退出登录</div>"

        self.assertTrue(is_login_timeout_page(TimeoutPage(), safe_page_content_fn=safe_page_content))

    def test_recover_login_timeout_page_clicks_mini_program_entry(self):
        class TimeoutPage:
            def __init__(self):
                self.url = "https://mp.weixin.qq.com/"
                self.recovered = False

            def wait_for_load_state(self, state=None, timeout=None):
                return None

            def wait_for_timeout(self, timeout):
                return None

            def locator(self, selector, **kwargs):
                if selector == "text=登录超时，请重新登录":
                    return FakeLocator(count=0 if self.recovered else 1)
                if selector == "text=小程序":
                    return FakeLocator(count=1, click_cb=self._recover)
                if selector == "text=退出登录":
                    return FakeLocator(count=1)
                return FakeLocator()

            def content(self):
                if self.recovered:
                    return '<div class="menu_box_account_info">账号设置</div>'
                return "<div>登录超时，请重新登录</div><div>小程序</div><div>退出登录</div>"

            def _recover(self):
                self.recovered = True
                self.url = "https://mp.weixin.qq.com/wxamp/index/index?token=1"

        page = TimeoutPage()
        recovered = recover_login_timeout_page(
            page,
            safe_page_content_fn=safe_page_content,
            wait_or_cancel_fn=lambda current_page, wait_ms, _is_cancelled=None: current_page.wait_for_timeout(wait_ms),
        )

        self.assertTrue(recovered)
        self.assertTrue(page.recovered)
        self.assertIn("token=1", page.url)

    def test_recover_wechat_mp_root_page_clicks_mini_program_entry(self):
        class RootPage:
            def __init__(self):
                self.url = "https://mp.weixin.qq.com/"
                self.recovered = False

            def wait_for_timeout(self, timeout):
                return None

            def locator(self, selector, **kwargs):
                if selector == "text=小程序":
                    return FakeLocator(count=1, click_cb=self._recover)
                return FakeLocator()

            def _recover(self):
                self.recovered = True
                self.url = "https://mp.weixin.qq.com/wxamp/index/index?token=1"

        page = RootPage()
        recovered = recover_wechat_mp_root_page(
            page,
            wait_or_cancel_fn=lambda current_page, wait_ms, _is_cancelled=None: current_page.wait_for_timeout(wait_ms),
        )

        self.assertTrue(recovered)
        self.assertTrue(page.recovered)
        self.assertIn("token=1", page.url)

    def test_is_wechat_mp_root_page_url_only_matches_plain_root_page(self):
        self.assertTrue(is_wechat_mp_root_page_url("https://mp.weixin.qq.com/"))
        self.assertTrue(is_wechat_mp_root_page_url("https://mp.weixin.qq.com/?lang=zh_CN"))
        self.assertFalse(is_wechat_mp_root_page_url("https://mp.weixin.qq.com/wxamp/index/index?token=1"))
        self.assertFalse(is_wechat_mp_root_page_url("https://mp.weixin.qq.com/?token=1"))

    def test_confirm_empty_refund_list_requires_second_confirmation(self):
        from desktop_py.core.fetcher_page_strategy import confirm_empty_refund_list

        page = FakePage()
        body_locator = FakeLocator(text="退款申请(0)")

        class FrameLocator:
            def locator(self, selector):
                return body_locator

        confirmed, latest_text = confirm_empty_refund_list(
            page=page,
            frame_locator=FrameLocator(),
            initial_text="退款申请(0)",
            captures=[],
            is_empty_refund_list_fn=lambda text: "退款申请(0)" in text,
            has_pending_refund_signal_fn=lambda text: "处理截止时间" in text,
            captures_indicate_non_empty_refunds_fn=lambda captures: False,
            wait_or_cancel_fn=lambda _page, _timeout_ms, _is_cancelled=None: None,
            retries=1,
            interval_ms=1,
        )

        self.assertTrue(confirmed)
        self.assertEqual(latest_text, "退款申请(0)")

    def test_confirm_empty_refund_list_ignores_weak_process_text_when_empty(self):
        from desktop_py.core.fetcher_page_strategy import (
            captures_indicate_non_empty_refunds,
            confirm_empty_refund_list,
            has_pending_refund_signal,
            is_empty_refund_list,
        )

        page = FakePage()
        body_locator = FakeLocator(text="退款申请(0) 处理 暂无内容")

        class FrameLocator:
            def locator(self, selector):
                return body_locator

        confirmed, latest_text = confirm_empty_refund_list(
            page=page,
            frame_locator=FrameLocator(),
            initial_text="退款申请(0) 处理 暂无内容",
            captures=[],
            is_empty_refund_list_fn=is_empty_refund_list,
            has_pending_refund_signal_fn=has_pending_refund_signal,
            captures_indicate_non_empty_refunds_fn=captures_indicate_non_empty_refunds,
            wait_or_cancel_fn=lambda _page, _timeout_ms, _is_cancelled=None: None,
            retries=1,
            interval_ms=1,
        )

        self.assertTrue(confirmed)
        self.assertEqual(latest_text, "退款申请(0) 处理 暂无内容")

    def test_confirm_empty_refund_list_keeps_deadline_as_strong_pending_signal(self):
        from desktop_py.core.fetcher_page_strategy import (
            captures_indicate_non_empty_refunds,
            confirm_empty_refund_list,
            has_pending_refund_signal,
            is_empty_refund_list,
        )

        page = FakePage()
        body_locator = FakeLocator(text="退款申请(0) 处理截止时间：2026-04-25 00:00:00")

        class FrameLocator:
            def locator(self, selector):
                return body_locator

        confirmed, latest_text = confirm_empty_refund_list(
            page=page,
            frame_locator=FrameLocator(),
            initial_text="退款申请(0) 处理截止时间：2026-04-25 00:00:00",
            captures=[],
            is_empty_refund_list_fn=is_empty_refund_list,
            has_pending_refund_signal_fn=has_pending_refund_signal,
            captures_indicate_non_empty_refunds_fn=captures_indicate_non_empty_refunds,
            wait_or_cancel_fn=lambda _page, _timeout_ms, _is_cancelled=None: None,
            retries=1,
            interval_ms=1,
        )

        self.assertFalse(confirmed)
        self.assertIn("处理截止时间", latest_text)

    def test_confirm_empty_refund_list_detects_late_pending_data(self):
        from desktop_py.core.fetcher_page_strategy import confirm_empty_refund_list

        page = FakePage()

        class BodyLocator:
            def __init__(self):
                self._values = ["退款申请(1) 处理截止时间：2026-04-25 00:00:00"]

            def text_content(self, timeout=None):
                return self._values[0]

        body_locator = BodyLocator()

        class FrameLocator:
            def locator(self, selector):
                return body_locator

        confirmed, latest_text = confirm_empty_refund_list(
            page=page,
            frame_locator=FrameLocator(),
            initial_text="退款申请(0)",
            captures=[],
            is_empty_refund_list_fn=lambda text: "退款申请(0)" in text,
            has_pending_refund_signal_fn=lambda text: "处理截止时间" in text or "退款申请(1)" in text,
            captures_indicate_non_empty_refunds_fn=lambda captures: False,
            wait_or_cancel_fn=lambda _page, _timeout_ms, _is_cancelled=None: None,
            retries=1,
            interval_ms=1,
        )

        self.assertFalse(confirmed)
        self.assertIn("处理截止时间", latest_text)

    def test_classify_refund_response_type_treats_ios_refund_list_as_list(self):
        response_type = classify_refund_response_type(
            "https://gamemp.weixin.qq.com/cgi-bin/gamewxagpaymgrwap/getiaprefundlist?token=1",
            {"data": {"list": [], "total_cnt": 0}},
        )

        self.assertEqual(response_type, "list")

    def test_list_capture_result_supports_ios_total_count_fields(self):
        from desktop_py.core.fetcher_page_strategy import list_capture_result

        empty_capture = {
            "response_type": "list",
            "body": {"data": {"list": [], "total_cnt": 0}},
        }
        non_empty_capture = {
            "response_type": "list",
            "body": {"data": {"list": [{"status_text": "待处理", "deadline_time": "2026-04-25 00:00:00"}], "total_cnt": 1}},
        }

        self.assertEqual(list_capture_result([empty_capture]), "empty")
        self.assertEqual(list_capture_result([non_empty_capture]), "non_empty")

    def test_confirm_empty_refund_list_detects_very_late_detail_before_accepting_empty(self):
        from desktop_py.core.fetcher_page_strategy import confirm_empty_refund_list

        page = FakePage()

        class BodyLocator:
            def __init__(self):
                self._values = [
                    "退款申请(0)",
                    "退款申请(0)",
                    "退款申请(0)",
                    "退款申请(0)",
                    "退款申请(1) 处理截止时间：2026-04-22 16:02:09",
                ]

            def text_content(self, timeout=None):
                if len(self._values) > 1:
                    return self._values.pop(0)
                return self._values[0]

        body_locator = BodyLocator()

        class FrameLocator:
            def locator(self, selector):
                return body_locator

        confirmed, latest_text = confirm_empty_refund_list(
            page=page,
            frame_locator=FrameLocator(),
            initial_text="退款申请(0)",
            captures=[],
            is_empty_refund_list_fn=lambda text: "退款申请(0)" in text,
            has_pending_refund_signal_fn=lambda text: "处理截止时间" in text or "退款申请(1)" in text,
            captures_indicate_non_empty_refunds_fn=lambda captures: False,
            wait_or_cancel_fn=lambda _page, _timeout_ms, _is_cancelled=None: None,
            retries=5,
            interval_ms=1,
        )

        self.assertFalse(confirmed)
        self.assertIn("处理截止时间", latest_text)

    def test_confirm_empty_refund_list_uses_capture_signal_to_block_false_empty(self):
        from desktop_py.core.fetcher_page_strategy import confirm_empty_refund_list

        page = FakePage()
        body_locator = FakeLocator(text="退款申请(0)")

        class FrameLocator:
            def locator(self, selector):
                return body_locator

        confirmed, latest_text = confirm_empty_refund_list(
            page=page,
            frame_locator=FrameLocator(),
            initial_text="退款申请(0)",
            captures=[{"body": {"data": {"appeal_deadline_time": "2026-04-25 00:00:00"}}}],
            is_empty_refund_list_fn=lambda text: "退款申请(0)" in text,
            has_pending_refund_signal_fn=lambda text: False,
            captures_indicate_non_empty_refunds_fn=lambda captures: True,
            wait_or_cancel_fn=lambda _page, _timeout_ms, _is_cancelled=None: None,
            retries=1,
            interval_ms=1,
        )

        self.assertFalse(confirmed)
        self.assertEqual(latest_text, "退款申请(0)")

    def test_confirm_empty_refund_list_prefers_non_empty_list_capture_over_empty_dom(self):
        from desktop_py.core.fetcher_page_strategy import confirm_empty_refund_list

        page = FakePage()
        body_locator = FakeLocator(text="退款申请(0)")

        class FrameLocator:
            def locator(self, selector):
                return body_locator

        confirmed, latest_text = confirm_empty_refund_list(
            page=page,
            frame_locator=FrameLocator(),
            initial_text="退款申请(0)",
            captures=[
                {
                    "response_type": "list",
                    "body": {
                        "data": {
                            "total_count": 1,
                            "user_refund_check_list": [
                                {"status_text": "待处理", "ctrl_info": {"deadline_time": "1777046400"}}
                            ],
                        }
                    },
                }
            ],
            is_empty_refund_list_fn=lambda text: "退款申请(0)" in text,
            has_pending_refund_signal_fn=lambda text: False,
            captures_indicate_non_empty_refunds_fn=lambda captures: False,
            wait_or_cancel_fn=lambda _page, _timeout_ms, _is_cancelled=None: None,
            retries=1,
            interval_ms=1,
        )

        self.assertFalse(confirmed)
        self.assertEqual(latest_text, "退款申请(0)")

    def test_confirm_empty_refund_list_prefers_empty_list_capture_when_dom_empty(self):
        from desktop_py.core.fetcher_page_strategy import confirm_empty_refund_list

        page = FakePage()
        body_locator = FakeLocator(text="退款申请(0)")

        class FrameLocator:
            def locator(self, selector):
                return body_locator

        confirmed, latest_text = confirm_empty_refund_list(
            page=page,
            frame_locator=FrameLocator(),
            initial_text="退款申请(0)",
            captures=[
                {
                    "response_type": "list",
                    "body": {"data": {"total_count": 0, "user_refund_check_list": []}},
                }
            ],
            is_empty_refund_list_fn=lambda text: "退款申请(0)" in text,
            has_pending_refund_signal_fn=lambda text: False,
            captures_indicate_non_empty_refunds_fn=lambda captures: False,
            wait_or_cancel_fn=lambda _page, _timeout_ms, _is_cancelled=None: None,
            retries=1,
            interval_ms=1,
        )

        self.assertTrue(confirmed)
        self.assertEqual(latest_text, "退款申请(0)")

    def test_confirm_empty_refund_list_uses_empty_capture_when_dom_lacks_count_marker(self):
        from desktop_py.core.fetcher_page_strategy import (
            captures_indicate_non_empty_refunds,
            confirm_empty_refund_list,
            has_pending_refund_signal,
            is_empty_refund_list,
        )

        page = FakePage()
        body_locator = FakeLocator(text="退款申请 处理 暂无待处理退款申请")

        class FrameLocator:
            def locator(self, selector):
                return body_locator

        confirmed, latest_text = confirm_empty_refund_list(
            page=page,
            frame_locator=FrameLocator(),
            initial_text="退款申请 处理 暂无待处理退款申请",
            captures=[
                {
                    "response_type": "list",
                    "body": {"data": {"user_refund_check_list": []}},
                }
            ],
            is_empty_refund_list_fn=is_empty_refund_list,
            has_pending_refund_signal_fn=has_pending_refund_signal,
            captures_indicate_non_empty_refunds_fn=captures_indicate_non_empty_refunds,
            wait_or_cancel_fn=lambda _page, _timeout_ms, _is_cancelled=None: None,
            retries=1,
            interval_ms=1,
        )

        self.assertTrue(confirmed)
        self.assertEqual(latest_text, "退款申请 处理 暂无待处理退款申请")

    def test_confirm_empty_refund_list_ignores_table_header_deadline_when_capture_empty(self):
        from desktop_py.core.fetcher_page_strategy import (
            captures_indicate_non_empty_refunds,
            confirm_empty_refund_list,
            has_pending_refund_signal,
            is_empty_refund_list,
        )

        page = FakePage()
        body_locator = FakeLocator(text="退款申请(0) 处理截止时间 操作 暂无内容")

        class FrameLocator:
            def locator(self, selector):
                return body_locator

        confirmed, latest_text = confirm_empty_refund_list(
            page=page,
            frame_locator=FrameLocator(),
            initial_text="退款申请(0) 处理截止时间 操作 暂无内容",
            captures=[
                {
                    "response_type": "list",
                    "body": {"data": {"total_count": 0, "user_refund_check_list": []}},
                }
            ],
            is_empty_refund_list_fn=is_empty_refund_list,
            has_pending_refund_signal_fn=has_pending_refund_signal,
            captures_indicate_non_empty_refunds_fn=captures_indicate_non_empty_refunds,
            wait_or_cancel_fn=lambda _page, _timeout_ms, _is_cancelled=None: None,
            retries=1,
            interval_ms=1,
        )

        self.assertTrue(confirmed)
        self.assertEqual(latest_text, "退款申请(0) 处理截止时间 操作 暂无内容")

    def test_confirm_empty_refund_list_keeps_positive_count_stronger_than_empty_capture(self):
        from desktop_py.core.fetcher_page_strategy import (
            captures_indicate_non_empty_refunds,
            confirm_empty_refund_list,
            has_pending_refund_signal,
            is_empty_refund_list,
        )

        page = FakePage()
        body_locator = FakeLocator(text="退款申请（1） 处理")

        class FrameLocator:
            def locator(self, selector):
                return body_locator

        confirmed, latest_text = confirm_empty_refund_list(
            page=page,
            frame_locator=FrameLocator(),
            initial_text="退款申请（1） 处理",
            captures=[
                {
                    "response_type": "list",
                    "body": {"data": {"total_count": 0, "user_refund_check_list": []}},
                }
            ],
            is_empty_refund_list_fn=is_empty_refund_list,
            has_pending_refund_signal_fn=has_pending_refund_signal,
            captures_indicate_non_empty_refunds_fn=captures_indicate_non_empty_refunds,
            wait_or_cancel_fn=lambda _page, _timeout_ms, _is_cancelled=None: None,
            retries=1,
            interval_ms=1,
        )

        self.assertFalse(confirmed)
        self.assertEqual(latest_text, "退款申请（1） 处理")

    def test_confirm_detail_deadline_retries_until_text_ready(self):
        from desktop_py.core.fetcher_page_strategy import confirm_detail_deadline

        page = FakePage()

        class BodyLocator:
            def __init__(self):
                self._texts = ["详情加载中", "处理截止时间：2026-04-25 00:00:00"]

            def text_content(self, timeout=None):
                if len(self._texts) > 1:
                    return self._texts.pop(0)
                return self._texts[0]

            def inner_html(self, timeout=None):
                return "<div>detail</div>"

        body_locator = BodyLocator()

        class FrameLocator:
            def locator(self, selector):
                return body_locator

        deadline_text, frame_text, _frame_html = confirm_detail_deadline(
            page=page,
            frame_locator=FrameLocator(),
            captures=[],
            feedback_url="https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=current",
            extract_labeled_datetime_fn=extract_labeled_datetime,
            fallback_from_responses_fn=lambda _captures: "",
            filter_detail_captures_fn=lambda captures, _feedback_url: captures,
            wait_or_cancel_fn=lambda _page, timeout_ms, _is_cancelled=None: page.wait_for_timeout(timeout_ms),
            retries=2,
            interval_ms=1,
        )

        self.assertEqual(deadline_text, "2026-04-25 00:00:00")
        self.assertIn("处理截止时间", frame_text)
        self.assertEqual(page.wait_calls, [1])

    def test_confirm_detail_deadline_default_window_tolerates_slow_first_load(self):
        from desktop_py.core.fetcher_page_strategy import confirm_detail_deadline

        page = FakePage()

        class BodyLocator:
            def __init__(self):
                self._texts = [
                    "详情加载中",
                    "详情加载中",
                    "详情加载中",
                    "详情加载中",
                    "详情加载中",
                    "详情加载中",
                    "处理截止时间：2026-04-22 16:02:09",
                ]

            def text_content(self, timeout=None):
                if len(self._texts) > 1:
                    return self._texts.pop(0)
                return self._texts[0]

            def inner_html(self, timeout=None):
                return "<div>detail</div>"

        body_locator = BodyLocator()

        class FrameLocator:
            def locator(self, selector):
                return body_locator

        deadline_text, frame_text, _frame_html = confirm_detail_deadline(
            page=page,
            frame_locator=FrameLocator(),
            captures=[],
            feedback_url="https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=current",
            extract_labeled_datetime_fn=extract_labeled_datetime,
            fallback_from_responses_fn=lambda _captures: "",
            filter_detail_captures_fn=lambda captures, _feedback_url: captures,
            wait_or_cancel_fn=lambda _page, timeout_ms, _is_cancelled=None: page.wait_for_timeout(timeout_ms),
        )

        self.assertEqual(deadline_text, "2026-04-22 16:02:09")
        self.assertIn("处理截止时间", frame_text)
        self.assertEqual(page.wait_calls, [1500, 1500, 1500, 1500, 1500, 1500])

    def test_confirm_detail_deadline_prefers_detail_capture_over_dom(self):
        from desktop_py.core.fetcher_page_strategy import confirm_detail_deadline, filter_detail_captures

        page = FakePage()

        class BodyLocator:
            def text_content(self, timeout=None):
                return "详情加载中"

            def inner_html(self, timeout=None):
                return "<div>loading</div>"

        class FrameLocator:
            def locator(self, selector):
                return BodyLocator()

        deadline_text, frame_text, _frame_html = confirm_detail_deadline(
            page=page,
            frame_locator=FrameLocator(),
            captures=[
                {
                    "response_type": "detail",
                    "url": "https://game.weixin.qq.com/cgi-bin/gamewxagbdatawap/getuserrefundchecklist?cid=abc",
                    "body": {"data": {"user_refund_check_list": [{"ctrl_info": {"deadline_time": "1777046400"}}]}},
                }
            ],
            feedback_url="https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=current",
            extract_labeled_datetime_fn=extract_labeled_datetime,
            fallback_from_responses_fn=_fallback_from_responses,
            filter_detail_captures_fn=filter_detail_captures,
            wait_or_cancel_fn=lambda _page, _timeout_ms, _is_cancelled=None: None,
            retries=0,
            interval_ms=1,
        )

        self.assertEqual(deadline_text, "2026-04-25 00:00:00")
        self.assertEqual(frame_text, "详情加载中")

    def test_confirm_detail_deadline_filters_previous_account_captures(self):
        from desktop_py.core.fetcher_page_strategy import confirm_detail_deadline, filter_detail_captures

        page = FakePage()

        class BodyLocator:
            def text_content(self, timeout=None):
                return "详情加载中"

            def inner_html(self, timeout=None):
                return "<div>detail</div>"

        class FrameLocator:
            def locator(self, selector):
                return BodyLocator()

        captures = [
            {
                "response_type": "detail",
                "token": "old",
                "url": "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=old",
                "body": {
                    "data": {"user_refund_check_list": [{"ctrl_info": {"appeal_deadline_time": "2026-04-22 16:02:09"}}]}
                },
            },
            {
                "response_type": "detail",
                "token": "current",
                "url": "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=current",
                "body": {
                    "data": {"user_refund_check_list": [{"ctrl_info": {"appeal_deadline_time": "2026-04-27 08:37:32"}}]}
                },
            },
        ]

        deadline_text, _frame_text, _frame_html = confirm_detail_deadline(
            page=page,
            frame_locator=FrameLocator(),
            captures=captures,
            feedback_url="https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=current",
            extract_labeled_datetime_fn=extract_labeled_datetime,
            fallback_from_responses_fn=_fallback_from_responses,
            filter_detail_captures_fn=filter_detail_captures,
            wait_or_cancel_fn=lambda _page, _timeout_ms, _is_cancelled=None: None,
            retries=0,
            interval_ms=1,
        )

        self.assertEqual(deadline_text, "2026-04-27 08:37:32")

    def test_filter_detail_captures_ignores_non_refund_urls_and_stale_tokens(self):
        from desktop_py.core.fetcher_page_strategy import filter_detail_captures

        captures = [
            "not a dict",
            {"response_type": "detail", "url": ""},
            {
                "response_type": "detail",
                "token": "old",
                "url": "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=old",
            },
            {
                "response_type": "unknown",
                "token": "current",
                "url": "https://example.com/metrics?token=current",
            },
            {
                "response_type": "detail",
                "token": "current",
                "url": "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=current",
            },
            {
                "response_type": "unknown",
                "token": "current",
                "url": "https://mp.weixin.qq.com/refund/api?token=current",
            },
        ]

        filtered = filter_detail_captures(
            captures,
            "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=current",
        )

        self.assertEqual([item["url"] for item in filtered], [captures[4]["url"], captures[5]["url"]])

    def test_extract_deadline_from_captures_prefers_nearest_deadline_across_detail_and_list(self):
        from desktop_py.core.fetcher_page_strategy import extract_deadline_from_captures

        captures = [
            {
                "response_type": "list",
                "body": {
                    "data": {
                        "user_refund_check_list": [
                            {"status_text": "待处理", "ctrl_info": {"deadline_time": "1777046400"}}
                        ]
                    }
                },
            },
            {
                "response_type": "detail",
                "body": {
                    "data": {"user_refund_check_list": [{"ctrl_info": {"appeal_deadline_time": "2026-04-27 08:37:32"}}]}
                },
            },
        ]

        self.assertEqual(extract_deadline_from_captures(captures), "2026-04-25 00:00:00")

    def test_extract_deadline_from_captures_includes_top_level_appeal_pending_item(self):
        from desktop_py.core.fetcher_page_strategy import extract_deadline_from_captures

        captures = [
            {
                "response_type": "list",
                "body": {
                    "data": {
                        "user_refund_check_list": [
                            {
                                "status_text": "申诉待处理",
                                "appeal_deadline_time": "2026-05-26 17:32:36",
                            },
                            {
                                "status_text": "待处理",
                                "ctrl_info": {"appeal_deadline_time": "2026-05-29 11:20:47"},
                            },
                        ]
                    }
                },
            },
            {
                "response_type": "detail",
                "body": {"data": {"appeal_deadline_time": "2026-05-29 11:20:47"}},
            },
        ]

        self.assertEqual(extract_deadline_from_captures(captures), "2026-05-26 17:32:36")

    def test_build_detail_result_uses_list_deadline_without_clicking_detail(self):
        from desktop_py.core.fetcher_page_strategy import build_detail_result

        captures = [
            {
                "response_type": "list",
                "token": "current",
                "url": "https://mp.weixin.qq.com/api/getUserRefundCheckList?token=current",
                "body": {
                    "data": {
                        "user_refund_check_list": [
                            {"status_text": "待处理", "ctrl_info": {"appeal_deadline_time": "2026-05-26 17:32:36"}},
                        ]
                    }
                },
            }
        ]

        class ActionLocator:
            def __init__(self):
                self.last = self

            def count(self):
                return 1

            def click(self, timeout=None):
                raise AssertionError("列表已提供截止时间时不应点击详情")

        class FrameLocator:
            def get_by_text(self, text, exact=False):
                return ActionLocator()

        class FakeContext:
            def storage_state(self, path=None, indexed_db=False):
                return None

        def fake_confirm_detail_deadline(**kwargs):
            raise AssertionError("列表已提供截止时间时不应确认详情")

        with TemporaryDirectory() as temp_dir:
            result = build_detail_result(
                page=object(),
                context=FakeContext(),
                account=AccountConfig(name="账号A", state_path="storage/a.json", is_entry_account=False),
                output_dir=Path(temp_dir),
                frame_locator=FrameLocator(),
                captures=captures,
                feedback_url="https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=current",
                profile_dir="",
                logger=None,
                safe_page_content_fn=lambda _page: "<html></html>",
                extract_current_account_name_fn=lambda _page: "账号A",
                confirm_detail_deadline_fn=fake_confirm_detail_deadline,
            )

        self.assertEqual(result.deadline_text, "2026-05-26 17:32:36")
        self.assertEqual(result.deadline_source, "list-capture")
        self.assertEqual(result.note, "已完成列表页抓取。")

    def test_build_detail_result_keeps_nearest_deadline_from_multiple_pending_refunds(self):
        from desktop_py.core.fetcher_page_strategy import build_detail_result

        captures = [
            {
                "response_type": "list",
                "token": "current",
                "url": "https://mp.weixin.qq.com/api/getUserRefundCheckList?token=current",
                "body": {
                    "data": {
                        "user_refund_check_list": [
                            {"status_text": "待处理", "ctrl_info": {"appeal_deadline_time": "2026-05-26 17:32:36"}},
                            {"status_text": "待处理", "ctrl_info": {"appeal_deadline_time": "2026-05-29 11:20:47"}},
                        ]
                    }
                },
            }
        ]

        class ActionLocator:
            def __init__(self):
                self.last = self

            def count(self):
                return 1

            def click(self, timeout=None):
                captures.append(
                    {
                        "response_type": "detail",
                        "token": "current",
                        "url": "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=current",
                        "body": {"data": {"appeal_deadline_time": "2026-05-29 11:20:47"}},
                    }
                )

        class FrameLocator:
            def get_by_text(self, text, exact=False):
                return ActionLocator()

        class FakeContext:
            def storage_state(self, path=None, indexed_db=False):
                return None

        def fake_confirm_detail_deadline(**kwargs):
            return _fallback_from_responses(kwargs["captures"]), "detail text", "<div>detail</div>"

        with TemporaryDirectory() as temp_dir:
            result = build_detail_result(
                page=object(),
                context=FakeContext(),
                account=AccountConfig(name="账号A", state_path="storage/a.json", is_entry_account=False),
                output_dir=Path(temp_dir),
                frame_locator=FrameLocator(),
                captures=captures,
                feedback_url="https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=current",
                profile_dir="",
                logger=None,
                safe_page_content_fn=lambda _page: "<html></html>",
                extract_current_account_name_fn=lambda _page: "账号A",
                confirm_detail_deadline_fn=fake_confirm_detail_deadline,
            )

        self.assertEqual(result.deadline_text, "2026-05-26 17:32:36")

    def test_build_detail_result_keeps_nearest_deadline_from_paginated_refund_list(self):
        from desktop_py.core.fetcher_page_strategy import build_detail_result, fetch_paginated_refund_list_captures

        captures = [
            {
                "response_type": "list",
                "token": "current",
                "url": "https://mp.weixin.qq.com/api/getUserRefundCheckList?token=current&cur_page=0&per_page=1",
                "body": {
                    "data": {
                        "total_count": 2,
                        "user_refund_check_list": [
                            {"status_text": "待处理", "ctrl_info": {"appeal_deadline_time": "2026-05-29 11:20:47"}},
                        ],
                    }
                },
            }
        ]

        def fake_request(_page, _request_url: str):
            return {
                "data": {
                    "total_count": 2,
                    "user_refund_check_list": [
                        {"status_text": "待处理", "ctrl_info": {"appeal_deadline_time": "2026-05-26 17:32:36"}},
                    ],
                }
            }

        captures = fetch_paginated_refund_list_captures(
            page=object(),
            captures=captures,
            logger=None,
            log_fn=lambda _logger, _message: None,
            request_refund_list_page_fn=fake_request,
        )

        class ActionLocator:
            def __init__(self):
                self.last = self

            def count(self):
                return 1

            def click(self, timeout=None):
                captures.append(
                    {
                        "response_type": "detail",
                        "token": "current",
                        "url": "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=current",
                        "body": {"data": {"appeal_deadline_time": "2026-05-29 11:20:47"}},
                    }
                )

        class FrameLocator:
            def get_by_text(self, text, exact=False):
                return ActionLocator()

        class FakeContext:
            def storage_state(self, path=None, indexed_db=False):
                return None

        def fake_confirm_detail_deadline(**kwargs):
            return _fallback_from_responses(kwargs["captures"]), "detail text", "<div>detail</div>"

        with TemporaryDirectory() as temp_dir:
            result = build_detail_result(
                page=object(),
                context=FakeContext(),
                account=AccountConfig(name="账号A", state_path="storage/a.json", is_entry_account=False),
                output_dir=Path(temp_dir),
                frame_locator=FrameLocator(),
                captures=captures,
                feedback_url="https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=current",
                profile_dir="",
                logger=None,
                safe_page_content_fn=lambda _page: "<html></html>",
                extract_current_account_name_fn=lambda _page: "账号A",
                confirm_detail_deadline_fn=fake_confirm_detail_deadline,
            )

        self.assertEqual(result.deadline_text, "2026-05-26 17:32:36")

    def test_captures_indicate_non_empty_refunds_does_not_treat_empty_count_as_pending(self):
        from desktop_py.core.fetcher_page_strategy import captures_indicate_non_empty_refunds

        captures = [
            {
                "response_type": "list",
                "body": {"data": {"count": 0, "total_count": 0, "user_refund_check_list": []}},
            }
        ]

        self.assertFalse(captures_indicate_non_empty_refunds(captures))

    def test_build_detail_result_only_uses_captures_after_action_click(self):
        from desktop_py.core.fetcher_page_strategy import build_detail_result

        captures = [
            {
                "url": "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=current",
                "body": {"data": {"appeal_deadline_time": "2026-04-22 16:02:09"}},
            }
        ]
        seen_captures: list[list[dict]] = []

        class ActionLocator:
            def __init__(self):
                self.last = self

            def count(self):
                return 1

            def click(self, timeout=None):
                captures.append(
                    {
                        "url": "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=current",
                        "body": {"data": {"appeal_deadline_time": "2026-04-27 08:37:32"}},
                    }
                )

        class FrameLocator:
            def get_by_text(self, text, exact=False):
                return ActionLocator()

        class FakeContext:
            def __init__(self):
                self.storage_state_calls: list[tuple[str | None, bool]] = []

            def storage_state(self, path=None, indexed_db=False):
                self.storage_state_calls.append((path, indexed_db))

        def fake_confirm_detail_deadline(**kwargs):
            seen_captures.append(list(kwargs["captures"]))
            return _fallback_from_responses(kwargs["captures"]), "detail text", "<div>detail</div>"

        context = FakeContext()
        with TemporaryDirectory() as temp_dir:
            result = build_detail_result(
                page=object(),
                context=context,
                account=AccountConfig(name="账号A", state_path="storage/a.json", is_entry_account=False),
                output_dir=Path(temp_dir),
                frame_locator=FrameLocator(),
                captures=captures,
                feedback_url="https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=current",
                profile_dir="",
                logger=None,
                safe_page_content_fn=lambda _page: "<html></html>",
                extract_current_account_name_fn=lambda _page: "账号A",
                confirm_detail_deadline_fn=fake_confirm_detail_deadline,
            )

        self.assertEqual(result.deadline_text, "2026-04-27 08:37:32")
        self.assertEqual(len(seen_captures), 1)
        self.assertEqual(len(seen_captures[0]), 1)
        self.assertEqual(
            _fallback_from_responses(seen_captures[0]),
            "2026-04-27 08:37:32",
        )
        self.assertEqual(context.storage_state_calls, [("storage\\a.json", True)])

    def test_resolve_frame_locator_error_has_code_and_html_evidence(self):
        from desktop_py.core.fetcher_page_strategy import resolve_frame_locator
        from desktop_py.core.fetcher_support import FetchError, FetchErrorCode

        page = FakePage()
        page.url = "https://mp.weixin.qq.com/"

        with (
            TemporaryDirectory() as temp_dir,
            patch("desktop_py.core.fetcher_page_strategy.write_account_output_text") as write_text,
        ):
            output_dir = Path(temp_dir) / "账号A"
            with self.assertRaises(FetchError) as raised:
                resolve_frame_locator(
                    page,
                    output_dir=output_dir,
                    business_iframe_selector_fn=lambda _page: "",
                    safe_page_content_fn=lambda _page: "<html>无 iframe</html>",
                )

        self.assertEqual(raised.exception.code, FetchErrorCode.BUSINESS_IFRAME_MISSING)
        self.assertEqual(raised.exception.evidence[0]["path"], str(output_dir / "page.html"))
        write_text.assert_called_with("账号A", "page.html", "<html>无 iframe</html>")

    def test_build_detail_result_without_deadline_returns_success_note(self):
        from desktop_py.core.fetcher_page_strategy import build_detail_result

        class EmptyActionLocator:
            def count(self):
                return 0

        class FrameLocator:
            def get_by_text(self, text, exact=False):
                return EmptyActionLocator()

        class FakeContext:
            def storage_state(self, path=None, indexed_db=False):
                return None

        with (
            TemporaryDirectory() as temp_dir,
            patch("desktop_py.core.fetcher_page_strategy.write_fetch_result") as write_fetch_result,
        ):
            output_dir = Path(temp_dir)
            result = build_detail_result(
                page=object(),
                context=FakeContext(),
                account=AccountConfig(name="账号A", state_path="storage/a.json", is_entry_account=False),
                output_dir=output_dir,
                frame_locator=FrameLocator(),
                captures=[],
                feedback_url="https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=current",
                profile_dir="",
                logger=None,
                safe_page_content_fn=lambda _page: "<html>详情页</html>",
                extract_current_account_name_fn=lambda _page: "账号A",
                confirm_detail_deadline_fn=lambda **_kwargs: ("", "无截止时间", "<div>无截止时间</div>"),
            )

        self.assertTrue(result.ok)
        self.assertEqual(result.deadline_text, "")
        self.assertEqual(result.note, "截止时间内无待处理")
        write_fetch_result.assert_called_once()

    def test_build_detail_result_prefers_action_response_contract_over_dom_text(self):
        from desktop_py.core.fetcher_page_strategy import (
            build_detail_result,
            confirm_detail_deadline,
            filter_detail_captures,
        )

        class ResponseInfo:
            def __init__(self, response):
                self.value = response

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        class ContractPage:
            def __init__(self):
                self.clicked = False
                self.response = FakeResponse(
                    '{"data":{"user_refund_check_list":[{"ctrl_info":{"appeal_deadline_time":"2026-04-27 08:37:32"}}]}}',
                    url="https://mp.weixin.qq.com/wxamp/cgi/getuserrefundchecklist?token=current&cid=abc",
                )

            def expect_response(self, predicate, timeout=None):
                self.predicate_matched = predicate(self.response)
                return ResponseInfo(self.response)

        class BodyLocator:
            def text_content(self, timeout=None):
                return "处理截止时间：2026-04-20 18:00"

            def inner_html(self, timeout=None):
                return "<div>处理截止时间：2026-04-20 18:00</div>"

        class FrameLocator:
            def __init__(self, page):
                self.page = page

            def get_by_text(self, text, exact=False):
                return FakeLocator(count=1, click_cb=lambda: setattr(self.page, "clicked", True))

            def locator(self, selector):
                return BodyLocator()

        class FakeContext:
            def __init__(self):
                self.storage_state_calls: list[tuple[str | None, bool]] = []

            def storage_state(self, path=None, indexed_db=False):
                self.storage_state_calls.append((path, indexed_db))

        page = ContractPage()
        context = FakeContext()
        with TemporaryDirectory() as temp_dir:
            result = build_detail_result(
                page=page,
                context=context,
                account=AccountConfig(name="账号A", state_path="storage/a.json", is_entry_account=False),
                output_dir=Path(temp_dir),
                frame_locator=FrameLocator(page),
                captures=[],
                feedback_url="https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=current",
                profile_dir="",
                logger=None,
                safe_page_content_fn=lambda _page: "<html></html>",
                extract_current_account_name_fn=lambda _page: "账号A",
                confirm_detail_deadline_fn=lambda **kwargs: confirm_detail_deadline(
                    **kwargs,
                    extract_labeled_datetime_fn=extract_labeled_datetime,
                    fallback_from_responses_fn=_fallback_from_responses,
                    filter_detail_captures_fn=filter_detail_captures,
                    wait_or_cancel_fn=lambda _page, _timeout_ms, _is_cancelled=None: None,
                ),
            )

        self.assertTrue(page.clicked)
        self.assertTrue(page.predicate_matched)
        self.assertEqual(result.deadline_text, "2026-04-27 08:37:32")

    def test_build_detail_result_falls_back_to_dom_when_action_response_times_out(self):
        from desktop_py.core.fetcher_page_strategy import (
            build_detail_result,
            confirm_detail_deadline,
            filter_detail_captures,
        )

        class TimeoutResponseInfo:
            value = None

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                raise RuntimeError("响应等待超时")

        class TimeoutPage:
            def __init__(self):
                self.clicked = False

            def expect_response(self, predicate, timeout=None):
                return TimeoutResponseInfo()

        class BodyLocator:
            def text_content(self, timeout=None):
                return "处理截止时间：2026-04-20 18:00"

            def inner_html(self, timeout=None):
                return "<div>处理截止时间：2026-04-20 18:00</div>"

        class FrameLocator:
            def __init__(self, page):
                self.page = page

            def get_by_text(self, text, exact=False):
                return FakeLocator(count=1, click_cb=lambda: setattr(self.page, "clicked", True))

            def locator(self, selector):
                return BodyLocator()

        class FakeContext:
            def __init__(self):
                self.storage_state_calls: list[tuple[str | None, bool]] = []

            def storage_state(self, path=None, indexed_db=False):
                self.storage_state_calls.append((path, indexed_db))

        page = TimeoutPage()
        context = FakeContext()
        with TemporaryDirectory() as temp_dir:
            result = build_detail_result(
                page=page,
                context=context,
                account=AccountConfig(name="账号A", state_path="storage/a.json", is_entry_account=False),
                output_dir=Path(temp_dir),
                frame_locator=FrameLocator(page),
                captures=[],
                feedback_url="https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=current",
                profile_dir="",
                logger=None,
                safe_page_content_fn=lambda _page: "<html></html>",
                extract_current_account_name_fn=lambda _page: "账号A",
                confirm_detail_deadline_fn=lambda **kwargs: confirm_detail_deadline(
                    **kwargs,
                    extract_labeled_datetime_fn=extract_labeled_datetime,
                    fallback_from_responses_fn=_fallback_from_responses,
                    filter_detail_captures_fn=filter_detail_captures,
                    wait_or_cancel_fn=lambda _page, _timeout_ms, _is_cancelled=None: None,
                ),
            )

        self.assertTrue(page.clicked)
        self.assertEqual(result.deadline_text, "2026-04-20 18:00")

    def test_build_empty_refund_result_persists_regular_state_file(self):
        from desktop_py.core.fetcher_page_strategy import build_empty_refund_result

        class FakeContext:
            def __init__(self):
                self.storage_state_calls: list[tuple[str | None, bool]] = []

            def storage_state(self, path=None, indexed_db=False):
                self.storage_state_calls.append((path, indexed_db))

        class FakeBodyLocator:
            def text_content(self, timeout=None):
                return "暂无内容"

        class FakeFrameLocator:
            def locator(self, selector):
                return FakeBodyLocator()

        context = FakeContext()
        with TemporaryDirectory() as temp_dir:
            result = build_empty_refund_result(
                page=object(),
                context=context,
                account=AccountConfig(name="账号A", state_path="storage/a.json", is_entry_account=False),
                output_dir=Path(temp_dir),
                frame_locator=FakeFrameLocator(),
                list_text="暂无内容",
                captures=[],
                feedback_url="https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=current",
                profile_dir="",
                logger=None,
                safe_page_content_fn=lambda _page: "<html></html>",
                extract_current_account_name_fn=lambda _page: "账号A",
                is_cancelled=None,
            )

        self.assertTrue(result.ok)
        self.assertEqual(result.note, "当前账号无待处理申请。")
        self.assertEqual(context.storage_state_calls, [("storage\\a.json", True)])

    def test_fetch_paginated_refund_list_captures_fetches_missing_pages(self):
        from desktop_py.core.fetcher_page_strategy import fetch_paginated_refund_list_captures

        requested_urls: list[str] = []
        logs: list[str] = []
        captures = [
            {
                "url": "https://mp.weixin.qq.com/api/getUserRefundCheckList?token=t&cur_page=0&per_page=1",
                "status": 200,
                "content_type": "application/json",
                "body": {
                    "data": {
                        "total_count": 2,
                        "user_refund_check_list": [{"ctrl_info": {"appeal_deadline_time": "2026-05-20 10:00:00"}}],
                    }
                },
                "token": "t",
                "response_type": "list",
            }
        ]

        def fake_request(_page, request_url: str):
            requested_urls.append(request_url)
            return {
                "data": {
                    "total_count": 2,
                    "user_refund_check_list": [{"ctrl_info": {"appeal_deadline_time": "2026-05-18 10:00:00"}}],
                }
            }

        result = fetch_paginated_refund_list_captures(
            page=object(),
            captures=captures,
            logger=logs.append,
            log_fn=lambda logger, message: logger(message),
            request_refund_list_page_fn=fake_request,
        )

        self.assertEqual(len(result), 2)
        self.assertIn("cur_page=1", requested_urls[0])
        self.assertIn("退款列表分页补抓成功：第 2/2 页。", logs)

    def test_extract_deadline_from_captures_prefers_earliest_paginated_deadline(self):
        from desktop_py.core.fetcher_page_strategy import extract_deadline_from_captures

        captures = [
            {
                "response_type": "list",
                "body": {
                    "data": {
                        "user_refund_check_list": [
                            {"status_text": "待处理", "ctrl_info": {"appeal_deadline_time": "2026-05-20 10:00:00"}}
                        ]
                    }
                },
            },
            {
                "response_type": "list",
                "body": {
                    "data": {
                        "user_refund_check_list": [
                            {"status_text": "待处理", "ctrl_info": {"appeal_deadline_time": "2026-05-18 10:00:00"}}
                        ]
                    }
                },
            },
        ]

        self.assertEqual(extract_deadline_from_captures(captures), "2026-05-18 10:00:00")
