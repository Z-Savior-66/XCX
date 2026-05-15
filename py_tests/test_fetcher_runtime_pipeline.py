from py_tests.fetcher_test_support import (
    AccountConfig,
    CancelledError,
    FakeLocator,
    FakePage,
    FetcherTestBase,
    FetchResult,
    Path,
    close_all_group_runtimes,
    fetch_account,
    fetch_account_in_page_impl,
    fetch_accounts_batch,
    patch,
    wait_or_cancel,
)


class FetcherRuntimePipelineTestCase(FetcherTestBase):
    def test_wait_or_cancel_raises_when_cancelled(self):
        page = FakePage()

        with self.assertRaisesRegex(CancelledError, "任务已取消"):
            wait_or_cancel(page, 200, lambda: True)

    def test_fetch_accounts_batch_groups_accounts_by_state_path(self):
        accounts = [
            AccountConfig(name="账号A", state_path="storage/a.json", is_entry_account=False),
            AccountConfig(name="账号B", state_path="storage/a.json", is_entry_account=False),
            AccountConfig(name="账号C", state_path="storage/b.json", is_entry_account=False),
        ]
        progress_calls: list[str] = []
        contexts = []

        with (
            patch("desktop_py.core.fetcher.sync_playwright") as mock_playwright,
            patch("desktop_py.core.fetcher.create_browser_context") as mock_create_context,
            patch(
                "desktop_py.core.fetcher._fetch_account_in_page",
                side_effect=lambda page, context, account, logger, profile_dir: type(
                    "Result", (), {"account_name": account.name}
                )(),
            ),
            patch("desktop_py.core.fetcher.Path.exists", return_value=True),
        ):
            mock_playwright.return_value.__enter__.return_value = object()
            for _ in range(2):
                fake_context = type(
                    "FakeContext",
                    (),
                    {
                        "new_page": lambda self: object(),
                        "storage_state": lambda self, path=None, indexed_db=False: None,
                        "close": lambda self: None,
                    },
                )()
                fake_browser = type("FakeBrowser", (), {"close": lambda self: None})()
                contexts.append((fake_browser, fake_context))
            mock_create_context.side_effect = contexts

            results = fetch_accounts_batch(accounts, progress=lambda result: progress_calls.append(result.account_name))

        self.assertEqual([result.account_name for result in results], ["账号A", "账号B", "账号C"])
        self.assertEqual(progress_calls, ["账号A", "账号B", "账号C"])
        self.assertEqual(mock_create_context.call_count, 2)

    def test_fetch_accounts_batch_creates_and_closes_single_page_per_group(self):
        accounts = [
            AccountConfig(name="账号A", state_path="storage/a.json", is_entry_account=False),
            AccountConfig(name="账号B", state_path="storage/a.json", is_entry_account=False),
        ]
        created_pages = []

        class FakePageObject:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

        class FakeContext:
            def new_page(self):
                page = FakePageObject()
                created_pages.append(page)
                return page

            def storage_state(self, path=None, indexed_db=False):
                return None

            def close(self):
                return None

        fake_context = FakeContext()
        fake_browser = type("FakeBrowser", (), {"close": lambda self: None})()

        with (
            patch("desktop_py.core.fetcher.sync_playwright") as mock_playwright,
            patch("desktop_py.core.fetcher.create_browser_context", return_value=(fake_browser, fake_context)),
            patch(
                "desktop_py.core.fetcher._fetch_account_in_page",
                side_effect=lambda page, context, account, logger, profile_dir: type(
                    "Result", (), {"account_name": account.name}
                )(),
            ),
            patch("desktop_py.core.fetcher.Path.exists", return_value=True),
        ):
            mock_playwright.return_value.__enter__.return_value = object()

            results = fetch_accounts_batch(accounts)
            close_all_group_runtimes()

        self.assertEqual([result.account_name for result in results], ["账号A", "账号B"])
        self.assertEqual(len(created_pages), 1)
        self.assertTrue(all(page.closed for page in created_pages))

    def test_fetch_accounts_batch_rebuilds_runtime_every_five_accounts(self):
        accounts = [
            AccountConfig(name=f"账号{i}", state_path="storage/a.json", is_entry_account=False) for i in range(6)
        ]
        created_pages = []

        class FakePageObject:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

        class FakeContext:
            def new_page(self):
                page = FakePageObject()
                created_pages.append(page)
                return page

            def storage_state(self, path=None, indexed_db=False):
                return None

            def close(self):
                return None

        fake_browser = type("FakeBrowser", (), {"close": lambda self: None})()

        with (
            patch("desktop_py.core.fetcher.sync_playwright") as mock_playwright,
            patch(
                "desktop_py.core.fetcher.create_browser_context",
                side_effect=[
                    (fake_browser, FakeContext()),
                    (fake_browser, FakeContext()),
                ],
            ) as mock_create_context,
            patch(
                "desktop_py.core.fetcher._fetch_account_in_page",
                side_effect=lambda page, context, account, logger, profile_dir, is_cancelled=None: FetchResult(
                    account_name=account.name,
                    ok=True,
                    actual_account_name=account.name,
                ),
            ),
            patch("desktop_py.core.fetcher.Path.exists", return_value=True),
        ):
            mock_playwright.return_value.__enter__.return_value = object()

            results = fetch_accounts_batch(accounts)

        self.assertEqual([result.account_name for result in results], [account.name for account in accounts])
        self.assertEqual(mock_create_context.call_count, 2)
        self.assertEqual(len(created_pages), 2)
        self.assertTrue(all(page.closed for page in created_pages))

    def test_fetch_account_reuses_existing_group_runtime(self):
        account = AccountConfig(name="账号A", state_path="storage/a.json", is_entry_account=False)
        created_pages = []

        class FakePageObject:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

        class FakeContext:
            def new_page(self):
                page = FakePageObject()
                created_pages.append(page)
                return page

            def storage_state(self, path=None, indexed_db=False):
                return None

            def close(self):
                return None

        fake_context = FakeContext()
        fake_browser = type("FakeBrowser", (), {"close": lambda self: None})()

        with (
            patch("desktop_py.core.fetcher.sync_playwright") as mock_playwright,
            patch(
                "desktop_py.core.fetcher.create_browser_context", return_value=(fake_browser, fake_context)
            ) as mock_create_context,
            patch(
                "desktop_py.core.fetcher._fetch_account_in_page",
                side_effect=lambda page, context, account, logger, profile_dir, is_cancelled=None: FetchResult(
                    account_name=account.name,
                    ok=True,
                    actual_account_name=account.name,
                ),
            ) as mock_fetch,
            patch("desktop_py.core.fetcher.Path.exists", return_value=True),
        ):
            mock_playwright.return_value.__enter__.return_value = object()

            first = fetch_account(account, 0)
            second = fetch_account(account, 0)
            close_all_group_runtimes()

        self.assertTrue(first.ok)
        self.assertTrue(second.ok)
        self.assertEqual(mock_create_context.call_count, 1)
        self.assertEqual(mock_fetch.call_count, 2)
        self.assertEqual(len(created_pages), 1)
        self.assertTrue(created_pages[0].closed)

    def test_fetch_account_and_batch_share_group_runtime(self):
        account = AccountConfig(name="账号A", state_path="storage/a.json", is_entry_account=False)
        created_pages = []

        class FakePageObject:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

        class FakeContext:
            def new_page(self):
                page = FakePageObject()
                created_pages.append(page)
                return page

            def storage_state(self, path=None, indexed_db=False):
                return None

            def close(self):
                return None

        fake_context = FakeContext()
        fake_browser = type("FakeBrowser", (), {"close": lambda self: None})()

        with (
            patch("desktop_py.core.fetcher.sync_playwright") as mock_playwright,
            patch(
                "desktop_py.core.fetcher.create_browser_context", return_value=(fake_browser, fake_context)
            ) as mock_create_context,
            patch(
                "desktop_py.core.fetcher._fetch_account_in_page",
                side_effect=lambda page, context, account, logger, profile_dir, is_cancelled=None: FetchResult(
                    account_name=account.name,
                    ok=True,
                    actual_account_name=account.name,
                ),
            ),
            patch("desktop_py.core.fetcher.Path.exists", return_value=True),
        ):
            mock_playwright.return_value.__enter__.return_value = object()

            single_result = fetch_account(account, 0)
            batch_results = fetch_accounts_batch([account])
            close_all_group_runtimes()

        self.assertTrue(single_result.ok)
        self.assertEqual([item.account_name for item in batch_results], ["账号A"])
        self.assertEqual(mock_create_context.call_count, 1)
        self.assertEqual(len(created_pages), 1)
        self.assertTrue(created_pages[0].closed)

    def test_fetch_account_in_page_uses_cached_current_account_name_without_reloading_home(self):
        calls = {
            "extract": 0,
            "switch": 0,
            "feedback": 0,
            "cleanup": 0,
        }

        class CachedPage:
            def __init__(self):
                self.url = (
                    "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?action=plugin_redirect&token=1"
                )
                self._current_account_name_cache = "账号A"
                self.goto_calls: list[str] = []

            def goto(self, url, wait_until=None, timeout=None):
                self.goto_calls.append(url)
                self.url = url

        test_case = self

        class FakeFrameLocator:
            def locator(self, selector):
                test_case.assertEqual(selector, "body")

                class FakeBodyLocator:
                    def text_content(self, timeout=None):
                        return "退款申请(0)"

                return FakeBodyLocator()

        page = CachedPage()
        account = AccountConfig(name="账号A", state_path="storage/a.json", is_entry_account=False)

        def fake_register_response_capture(_page, _capture):
            return [], lambda: calls.__setitem__("cleanup", calls["cleanup"] + 1)

        def fake_extract_current_account_name(_page):
            calls["extract"] += 1
            return "账号A"

        def fake_switch_to_account(_page, _account_name, _home_url, _logger):
            calls["switch"] += 1

        def fake_open_feedback_page(_page, **_kwargs):
            calls["feedback"] += 1
            return "https://example.com/detail"

        result = fetch_account_in_page_impl(
            page,
            object(),
            account,
            None,
            "",
            None,
            account_output_dir_fn=lambda _account_name: Path("output") / "账号A",
            register_response_capture_fn=fake_register_response_capture,
            capture_response_payload_fn=lambda response: response,
            resolve_bootstrap_url_fn=lambda _account, _output_dir: _account.home_url,
            wait_for_url_contains_fn=lambda *_args, **_kwargs: True,
            extract_current_account_name_fn=fake_extract_current_account_name,
            should_switch_for_account_fn=lambda _account, current_account_name: current_account_name != _account.name,
            switch_to_account_fn=fake_switch_to_account,
            log_fn=lambda _logger, _message: None,
            open_feedback_page_fn=fake_open_feedback_page,
            build_feedback_url_fn=lambda page_url: page_url,
            wait_for_iframe_ready_fn=lambda *_args, **_kwargs: True,
            resolve_frame_locator_fn=lambda *_args, **_kwargs: FakeFrameLocator(),
            business_iframe_selector_fn=lambda _page: "#js_iframe",
            safe_page_content_fn=lambda _page: "<html></html>",
            is_empty_refund_list_fn=lambda list_text: "退款申请(0)" in list_text,
            confirm_empty_refund_list_fn=lambda **kwargs: (True, kwargs["initial_text"]),
            build_empty_refund_result_fn=lambda **kwargs: FetchResult(
                account_name=kwargs["account"].name,
                ok=True,
                actual_account_name=kwargs["account"].name,
                page_url=kwargs["feedback_url"],
            ),
            build_detail_result_fn=lambda **kwargs: FetchResult(
                account_name=kwargs["account"].name,
                ok=True,
                actual_account_name=kwargs["account"].name,
                page_url=kwargs["feedback_url"],
            ),
        )

        self.assertTrue(result.ok)
        self.assertEqual(page.goto_calls, [])
        self.assertEqual(calls["extract"], 0)
        self.assertEqual(calls["switch"], 0)
        self.assertEqual(calls["feedback"], 1)
        self.assertEqual(calls["cleanup"], 1)

    def test_fetch_account_in_page_rechecks_empty_list_before_marking_empty(self):
        class EmptyThenDataPage:
            def __init__(self):
                self.url = (
                    "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?action=plugin_redirect&token=1"
                )

        class SequencedBodyLocator:
            def __init__(self, values: list[str]):
                self._values = list(values)

            def text_content(self, timeout=None):
                if len(self._values) > 1:
                    return self._values.pop(0)
                return self._values[0]

            def inner_html(self, timeout=None):
                return "<div>ok</div>"

        class SequencedFrameLocator:
            def __init__(self, body_locator):
                self._body_locator = body_locator

            def locator(self, selector):
                test_case.assertEqual(selector, "body")
                return self._body_locator

            def get_by_text(self, _text, exact=False):
                return FakeLocator(count=0)

        test_case = self
        page = EmptyThenDataPage()
        account = AccountConfig(name="账号A", state_path="storage/a.json", is_entry_account=False)
        body_locator = SequencedBodyLocator(["退款申请(0)", "退款申请(1) 处理截止时间：2026-04-25 00:00:00"])
        frame_locator = SequencedFrameLocator(body_locator)
        empty_called = {"value": False}
        detail_called = {"value": False}

        result = fetch_account_in_page_impl(
            page,
            object(),
            account,
            None,
            "",
            None,
            account_output_dir_fn=lambda _account_name: Path("output") / "账号A",
            register_response_capture_fn=lambda _page, _capture: ([], lambda: None),
            capture_response_payload_fn=lambda response: response,
            resolve_bootstrap_url_fn=lambda _account, _output_dir: _account.home_url,
            wait_for_url_contains_fn=lambda *_args, **_kwargs: True,
            extract_current_account_name_fn=lambda _page: "账号A",
            should_switch_for_account_fn=lambda _account, _current_account_name: False,
            switch_to_account_fn=lambda *_args, **_kwargs: None,
            log_fn=lambda *_args, **_kwargs: None,
            open_feedback_page_fn=lambda _page, **_kwargs: "https://example.com/detail",
            build_feedback_url_fn=lambda page_url: page_url,
            wait_for_iframe_ready_fn=lambda *_args, **_kwargs: True,
            resolve_frame_locator_fn=lambda *_args, **_kwargs: frame_locator,
            business_iframe_selector_fn=lambda _page: "#js_iframe",
            safe_page_content_fn=lambda _page: "<html></html>",
            is_empty_refund_list_fn=lambda list_text: "退款申请(0)" in list_text,
            confirm_empty_refund_list_fn=lambda **kwargs: (
                False,
                kwargs["frame_locator"].locator("body").text_content(),
            ),
            build_empty_refund_result_fn=lambda **kwargs: (
                empty_called.__setitem__("value", True)
                or FetchResult(
                    account_name=kwargs["account"].name,
                    ok=True,
                    actual_account_name=kwargs["account"].name,
                    page_url=kwargs["feedback_url"],
                )
            ),
            build_detail_result_fn=lambda **kwargs: (
                detail_called.__setitem__("value", True)
                or FetchResult(
                    account_name=kwargs["account"].name,
                    ok=True,
                    actual_account_name=kwargs["account"].name,
                    deadline_text="2026-04-25 00:00:00",
                    page_url=kwargs["feedback_url"],
                )
            ),
        )

        self.assertTrue(result.ok)
        self.assertFalse(empty_called["value"])
        self.assertTrue(detail_called["value"])

    def test_fetch_account_in_page_only_passes_feedback_window_captures(self):
        class DemoPage:
            def __init__(self):
                self.url = "https://mp.weixin.qq.com/wxamp/index/index?token=1"

        page = DemoPage()
        account = AccountConfig(name="账号A", state_path="storage/a.json", is_entry_account=False)
        captures = [
            {"response_type": "list", "body": {"data": {"total_count": 0, "user_refund_check_list": []}}},
        ]
        seen_confirm_captures: list[list[dict]] = []

        class FrameLocator:
            def locator(self, selector):
                return FakeLocator(text="退款申请(0)")

            def get_by_text(self, text, exact=False):
                return FakeLocator(count=0)

        def fake_open_feedback_page(_page, **_kwargs):
            captures.append(
                {
                    "response_type": "list",
                    "body": {
                        "data": {
                            "total_count": 1,
                            "user_refund_check_list": [{"ctrl_info": {"deadline_time": "1777046400"}}],
                        }
                    },
                }
            )
            return "https://example.com/detail"

        result = fetch_account_in_page_impl(
            page,
            object(),
            account,
            None,
            "",
            None,
            account_output_dir_fn=lambda _account_name: Path("output") / "账号A",
            register_response_capture_fn=lambda _page, _capture: (captures, lambda: None),
            capture_response_payload_fn=lambda response: response,
            resolve_bootstrap_url_fn=lambda _account, _output_dir: _account.home_url,
            wait_for_url_contains_fn=lambda *_args, **_kwargs: True,
            extract_current_account_name_fn=lambda _page: "账号A",
            should_switch_for_account_fn=lambda _account, _current_account_name: False,
            switch_to_account_fn=lambda *_args, **_kwargs: None,
            log_fn=lambda *_args, **_kwargs: None,
            open_feedback_page_fn=fake_open_feedback_page,
            build_feedback_url_fn=lambda page_url: page_url,
            wait_for_iframe_ready_fn=lambda *_args, **_kwargs: True,
            resolve_frame_locator_fn=lambda *_args, **_kwargs: FrameLocator(),
            business_iframe_selector_fn=lambda _page: "#js_iframe",
            safe_page_content_fn=lambda _page: "<html></html>",
            is_empty_refund_list_fn=lambda list_text: "退款申请(0)" in list_text,
            confirm_empty_refund_list_fn=lambda **kwargs: (
                seen_confirm_captures.append(list(kwargs["captures"])) or (False, kwargs["initial_text"])
            ),
            build_empty_refund_result_fn=lambda **kwargs: FetchResult(
                account_name=kwargs["account"].name,
                ok=True,
                actual_account_name=kwargs["account"].name,
                page_url=kwargs["feedback_url"],
            ),
            build_detail_result_fn=lambda **kwargs: FetchResult(
                account_name=kwargs["account"].name,
                ok=True,
                actual_account_name=kwargs["account"].name,
                deadline_text="2026-04-25 00:00:00",
                page_url=kwargs["feedback_url"],
            ),
        )

        self.assertTrue(result.ok)
        self.assertEqual(len(seen_confirm_captures), 1)
        self.assertEqual(len(seen_confirm_captures[0]), 1)
        self.assertEqual(seen_confirm_captures[0][0]["body"]["data"]["total_count"], 1)

    def test_fetch_account_in_page_appends_notification_summary(self):
        class DemoPage:
            def __init__(self):
                self.url = "https://mp.weixin.qq.com/wxamp/index/index?token=1"

        page = DemoPage()
        account = AccountConfig(name="账号A", state_path="storage/a.json", is_entry_account=False)

        class FrameLocator:
            def locator(self, selector):
                return FakeLocator(text="退款申请(0)")

            def get_by_text(self, text, exact=False):
                return FakeLocator(count=0)

        result = fetch_account_in_page_impl(
            page,
            object(),
            account,
            None,
            "",
            None,
            account_output_dir_fn=lambda _account_name: Path("output") / "账号A",
            register_response_capture_fn=lambda _page, _capture: ([], lambda: None),
            capture_response_payload_fn=lambda response: response,
            resolve_bootstrap_url_fn=lambda _account, _output_dir: _account.home_url,
            wait_for_url_contains_fn=lambda *_args, **_kwargs: True,
            extract_current_account_name_fn=lambda _page: "账号A",
            should_switch_for_account_fn=lambda _account, _current_account_name: False,
            switch_to_account_fn=lambda *_args, **_kwargs: None,
            log_fn=lambda *_args, **_kwargs: None,
            open_feedback_page_fn=lambda _page, **_kwargs: "https://example.com/detail",
            build_feedback_url_fn=lambda page_url: page_url,
            wait_for_iframe_ready_fn=lambda *_args, **_kwargs: True,
            resolve_frame_locator_fn=lambda *_args, **_kwargs: FrameLocator(),
            business_iframe_selector_fn=lambda _page: "#js_iframe",
            safe_page_content_fn=lambda _page: "<html></html>",
            fetch_notifications_fn=lambda *_args, **_kwargs: {
                "ok": True,
                "notifications": [{"title": "小程序微信认证年审通知"}],
                "summary": "通知中心未读消息 1 条：小程序微信认证年审通知",
                "page_url": "https://example.com/notice",
            },
            is_empty_refund_list_fn=lambda list_text: "退款申请(0)" in list_text,
            confirm_empty_refund_list_fn=lambda **kwargs: (True, kwargs["initial_text"]),
            build_empty_refund_result_fn=lambda **kwargs: FetchResult(
                account_name=kwargs["account"].name,
                ok=True,
                actual_account_name=kwargs["account"].name,
                page_url=kwargs["feedback_url"],
            ),
            build_detail_result_fn=lambda **kwargs: FetchResult(
                account_name=kwargs["account"].name,
                ok=True,
                actual_account_name=kwargs["account"].name,
                page_url=kwargs["feedback_url"],
            ),
        )

        self.assertTrue(result.ok)
        self.assertIn("通知中心未读消息 1 条：小程序微信认证年审通知", result.note)

    def test_fetch_account_in_page_recovers_login_timeout_screen_before_opening_feedback(self):
        class TimeoutThenReadyPage:
            def __init__(self):
                self.url = "https://mp.weixin.qq.com/"
                self.recovered = False
                self.goto_calls: list[str] = []

            def goto(self, url, wait_until=None, timeout=None):
                self.goto_calls.append(url)
                self.url = url

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

        page = TimeoutThenReadyPage()
        account = AccountConfig(name="账号A", state_path="storage/a.json", is_entry_account=False)

        class FakeFrameLocator:
            def locator(self, selector):
                return FakeLocator(text="退款申请(0)")

            def get_by_text(self, text, exact=False):
                return FakeLocator(count=0)

        result = fetch_account_in_page_impl(
            page,
            object(),
            account,
            None,
            "",
            None,
            account_output_dir_fn=lambda _account_name: Path("output") / "账号A",
            register_response_capture_fn=lambda _page, _capture: ([], lambda: None),
            capture_response_payload_fn=lambda response: response,
            resolve_bootstrap_url_fn=lambda _account, _output_dir: _account.home_url,
            wait_for_url_contains_fn=lambda current_page, keywords, timeout_ms=0, is_cancelled=None: any(
                keyword in current_page.url for keyword in keywords
            ),
            extract_current_account_name_fn=lambda _page: "账号A",
            should_switch_for_account_fn=lambda _account, _current_account_name: False,
            switch_to_account_fn=lambda *_args, **_kwargs: None,
            log_fn=lambda *_args, **_kwargs: None,
            open_feedback_page_fn=lambda _page, **_kwargs: "https://example.com/detail",
            build_feedback_url_fn=lambda page_url: page_url,
            wait_for_iframe_ready_fn=lambda *_args, **_kwargs: True,
            resolve_frame_locator_fn=lambda *_args, **_kwargs: FakeFrameLocator(),
            business_iframe_selector_fn=lambda _page: "#js_iframe",
            safe_page_content_fn=lambda current_page: current_page.content(),
            is_empty_refund_list_fn=lambda list_text: "退款申请(0)" in list_text,
            confirm_empty_refund_list_fn=lambda **kwargs: (True, kwargs["initial_text"]),
            build_empty_refund_result_fn=lambda **kwargs: FetchResult(
                account_name=kwargs["account"].name,
                ok=True,
                actual_account_name=kwargs["account"].name,
                page_url=kwargs["feedback_url"],
            ),
            build_detail_result_fn=lambda **kwargs: FetchResult(
                account_name=kwargs["account"].name,
                ok=True,
                actual_account_name=kwargs["account"].name,
                page_url=kwargs["feedback_url"],
            ),
        )

        self.assertTrue(result.ok)
        self.assertTrue(page.recovered)
        self.assertIn("https://mp.weixin.qq.com/", page.goto_calls)

    def test_fetch_accounts_batch_stops_gracefully_when_cancelled(self):
        accounts = [
            AccountConfig(name="账号A", state_path="storage/a.json", is_entry_account=False),
            AccountConfig(name="账号B", state_path="storage/a.json", is_entry_account=False),
        ]
        progress_calls: list[str] = []

        class FakePageObject:
            def close(self):
                return None

        class FakeContext:
            def new_page(self):
                return FakePageObject()

            def storage_state(self, path=None, indexed_db=False):
                return None

            def close(self):
                return None

        fake_context = FakeContext()
        fake_browser = type("FakeBrowser", (), {"close": lambda self: None})()
        results = [
            type("Result", (), {"account_name": "账号A"})(),
            CancelledError("任务已取消"),
        ]

        def fake_fetch(page, context, account, logger, profile_dir, is_cancelled=None):
            result = results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

        with (
            patch("desktop_py.core.fetcher.sync_playwright") as mock_playwright,
            patch("desktop_py.core.fetcher.create_browser_context", return_value=(fake_browser, fake_context)),
            patch("desktop_py.core.fetcher._fetch_account_in_page", side_effect=fake_fetch),
            patch("desktop_py.core.fetcher.Path.exists", return_value=True),
        ):
            mock_playwright.return_value.__enter__.return_value = object()
            with self.assertRaisesRegex(CancelledError, "任务已取消"):
                fetch_accounts_batch(
                    accounts,
                    progress=lambda result: progress_calls.append(result.account_name),
                )

        self.assertEqual(progress_calls, ["账号A"])

    def test_fetch_accounts_batch_does_not_rebuild_runtime_after_last_fatal_error(self):
        from desktop_py.core.fetcher_pipeline import fetch_accounts_batch_impl

        accounts = [AccountConfig(name="账号A", state_path="storage/a.json", is_entry_account=False)]
        acquire_calls = 0
        invalidated_messages: list[str] = []

        class FakeRuntime:
            def __init__(self):
                self.page = object()
                self.context = object()
                self.valid = True
                self.busy = True

        def acquire_runtime(*_args, **_kwargs):
            nonlocal acquire_calls
            acquire_calls += 1
            if acquire_calls > 1:
                raise RuntimeError("不应为最后一个账号重建运行时")
            return FakeRuntime()

        def invalidate_runtime(runtime, message=""):
            runtime.valid = False
            runtime.busy = False
            invalidated_messages.append(message)

        def fetch_account_in_page(*_args, **_kwargs):
            raise RuntimeError("target page, context or browser has been closed")

        results = fetch_accounts_batch_impl(
            accounts,
            sync_playwright_fn=lambda: None,
            path_exists_fn=lambda _path: True,
            validate_shared_browser_profile_dir_fn=lambda value: value,
            create_browser_context_fn=lambda *_args: (None, None),
            validate_account_state_fn=lambda *_args, **_kwargs: True,
            renew_account_state_fn=lambda *_args, **_kwargs: True,
            fetch_account_in_page_fn=fetch_account_in_page,
            acquire_group_runtime_fn=acquire_runtime,
            release_group_runtime_fn=lambda _runtime: None,
            invalidate_group_runtime_fn=invalidate_runtime,
            update_runtime_current_account_name_fn=lambda _runtime, _name: None,
            should_invalidate_runtime_fn=lambda _exc: True,
        )

        self.assertEqual(acquire_calls, 1)
        self.assertEqual(len(invalidated_messages), 1)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].ok)
        self.assertEqual(results[0].account_name, "账号A")
        self.assertIn("target page, context or browser has been closed", results[0].note)

    def test_fetch_accounts_batch_rebuilds_runtime_after_non_last_fatal_error(self):
        from desktop_py.core.fetcher_pipeline import fetch_accounts_batch_impl

        accounts = [
            AccountConfig(name="账号A", state_path="storage/a.json", is_entry_account=False),
            AccountConfig(name="账号B", state_path="storage/a.json", is_entry_account=False),
        ]
        acquire_calls = 0
        invalidated_messages: list[str] = []

        class FakeRuntime:
            def __init__(self, runtime_id: int):
                self.page = object()
                self.context = object()
                self.valid = True
                self.busy = True
                self.runtime_id = runtime_id

        def acquire_runtime(*_args, **_kwargs):
            nonlocal acquire_calls
            acquire_calls += 1
            return FakeRuntime(acquire_calls)

        def invalidate_runtime(runtime, message=""):
            runtime.valid = False
            runtime.busy = False
            invalidated_messages.append(message)

        def fetch_account_in_page(_page, _context, account, *_args):
            if account.name == "账号A":
                raise RuntimeError("target page, context or browser has been closed")
            return FetchResult(account_name=account.name, ok=True, actual_account_name=account.name)

        results = fetch_accounts_batch_impl(
            accounts,
            sync_playwright_fn=lambda: None,
            path_exists_fn=lambda _path: True,
            validate_shared_browser_profile_dir_fn=lambda value: value,
            create_browser_context_fn=lambda *_args: (None, None),
            validate_account_state_fn=lambda *_args, **_kwargs: True,
            renew_account_state_fn=lambda *_args, **_kwargs: True,
            fetch_account_in_page_fn=fetch_account_in_page,
            acquire_group_runtime_fn=acquire_runtime,
            release_group_runtime_fn=lambda _runtime: None,
            invalidate_group_runtime_fn=invalidate_runtime,
            update_runtime_current_account_name_fn=lambda _runtime, _name: None,
            should_invalidate_runtime_fn=lambda _exc: True,
        )

        self.assertEqual(acquire_calls, 2)
        self.assertEqual(len(results), 2)
        self.assertFalse(results[0].ok)
        self.assertEqual(results[0].account_name, "账号A")
        self.assertTrue(results[1].ok)
        self.assertEqual(results[1].account_name, "账号B")
        self.assertIn("target page, context or browser has been closed", invalidated_messages[0])
