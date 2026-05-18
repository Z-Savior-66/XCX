from py_tests.fetcher_test_support import (
    AccountConfig,
    FakeLocator,
    FakePage,
    FetcherTestBase,
    Path,
    TemporaryDirectory,
    find_switch_entry,
    patch,
    prepare_switch_account_page,
    resolve_bootstrap_url,
    should_retry_switch_from_home,
    should_switch_account,
    should_switch_for_account,
    wait_for_account_switch_stable,
    wait_for_current_account_name,
    wait_for_switch_account_items,
    wait_for_url_contains,
)


class FetcherSwitchingTestCase(FetcherTestBase):
    def test_find_switch_entry_prefers_title_selector(self):
        title_locator = FakeLocator(count=1)
        fallback_locator = FakeLocator(count=1)
        page = FakePage(
            locator_map={
                ("div.menu_box_account_info_item[title='切换账号']", None): title_locator,
                (".menu_box_account_info_item", "切换账号"): fallback_locator,
            }
        )

        result = find_switch_entry(page)

        self.assertIs(result, title_locator)

    def test_find_switch_entry_falls_back_to_text_locator(self):
        text_locator = FakeLocator(count=1)
        page = FakePage(
            locator_map={
                ("div.menu_box_account_info_item[title='切换账号']", None): FakeLocator(),
                (".menu_box_account_info_item", "切换账号"): FakeLocator(),
                ("[title='切换账号']", None): FakeLocator(),
            },
            text_map={
                ("切换账号", True): text_locator,
            },
        )

        result = find_switch_entry(page)

        self.assertIs(result, text_locator)

    def test_find_switch_entry_returns_none_when_missing(self):
        page = FakePage()

        result = find_switch_entry(page)

        self.assertIsNone(result)

    def test_should_switch_account(self):
        self.assertFalse(should_switch_account("七色花消消乐", "七色花消消乐"))
        self.assertTrue(should_switch_account("主账号", "七色花消消乐"))
        self.assertTrue(should_switch_account("", "七色花消消乐"))

    def test_should_switch_for_entry_account(self):
        account = AccountConfig(name="主账号", state_path="storage/shared.json", is_entry_account=True)

        self.assertFalse(should_switch_for_account(account, ""))
        self.assertFalse(should_switch_for_account(account, "七色花消消乐"))

    def test_should_switch_for_imported_account(self):
        account = AccountConfig(name="七色花消消乐", state_path="storage/shared.json", is_entry_account=False)

        self.assertFalse(should_switch_for_account(account, "七色花消消乐"))
        self.assertTrue(should_switch_for_account(account, "不灭轮回"))
        self.assertTrue(should_switch_for_account(account, ""))

    def test_should_retry_switch_from_home(self):
        self.assertTrue(
            should_retry_switch_from_home(
                "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?action=plugin_redirect&token=1",
                "https://mp.weixin.qq.com/",
                False,
            )
        )

    def test_resolve_bootstrap_url_uses_home_url_when_feedback_url_exists(self):
        account = AccountConfig(
            name="导入账号",
            state_path="storage/shared.json",
            is_entry_account=False,
            feedback_url="https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?action=plugin_redirect&token=old",
            home_url="https://mp.weixin.qq.com/",
        )

        self.assertEqual(resolve_bootstrap_url(account, Path("output/demo")), "https://mp.weixin.qq.com/")

    def test_resolve_bootstrap_url_ignores_stale_result_page_url(self):
        account = AccountConfig(
            name="导入账号",
            state_path="storage/shared.json",
            is_entry_account=False,
            home_url="https://mp.weixin.qq.com/",
        )
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            (output_dir / "result.json").write_text(
                '{"page_url": "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?action=plugin_redirect&token=old"}',
                encoding="utf-8",
            )

            self.assertEqual(resolve_bootstrap_url(account, output_dir), "https://mp.weixin.qq.com/")
        self.assertFalse(
            should_retry_switch_from_home(
                "https://mp.weixin.qq.com/",
                "https://mp.weixin.qq.com/",
                False,
            )
        )
        self.assertFalse(
            should_retry_switch_from_home(
                "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?action=plugin_redirect&token=1",
                "https://mp.weixin.qq.com/",
                True,
            )
        )

    def test_wait_for_switch_account_items_retries_until_success(self):
        account_locator = FakeLocator(counts=[0, 0, 0, 0, 0, 0, 0, 0, 0, 2])
        close_locator = FakeLocator(count=1)
        page = FakePage(
            locator_map={
                (".switch_account_dialog .account_item", None): account_locator,
                (".switch_account_dialog .close_icon", None): close_locator,
                ("div.menu_box_account_info_item[title='切换账号']", None): FakeLocator(count=1),
            }
        )
        logs: list[str] = []

        with patch("desktop_py.core.fetcher.open_switch_account_dialog"):
            result = wait_for_switch_account_items(page, ".switch_account_dialog .account_item", logs.append)

        self.assertIs(result, account_locator)
        self.assertGreaterEqual(len(page.wait_calls), 8)
        self.assertEqual(logs, [])

    def test_wait_for_switch_account_items_raises_after_three_attempts(self):
        page = FakePage(
            locator_map={
                (".switch_account_dialog .account_item", None): FakeLocator(counts=[0] * 40),
                (".switch_account_dialog .close_icon", None): FakeLocator(count=1),
                ("div.menu_box_account_info_item[title='切换账号']", None): FakeLocator(count=1),
            }
        )

        with patch("desktop_py.core.fetcher.open_switch_account_dialog"):
            with self.assertRaisesRegex(Exception, "未读取到切换账号列表，已重试 3 次。"):
                wait_for_switch_account_items(page, ".switch_account_dialog .account_item")

    def test_wait_for_switch_account_items_waits_before_first_retry_log(self):
        account_locator = FakeLocator(counts=[0, 0, 0, 0, 0, 0, 0, 0, 1])
        page = FakePage(
            locator_map={
                (".switch_account_dialog .account_item", None): account_locator,
                (".switch_account_dialog .close_icon", None): FakeLocator(count=1),
                ("div.menu_box_account_info_item[title='切换账号']", None): FakeLocator(count=1),
            }
        )
        logs: list[str] = []

        with patch("desktop_py.core.fetcher.open_switch_account_dialog"):
            result = wait_for_switch_account_items(page, ".switch_account_dialog .account_item", logs.append)

        self.assertIs(result, account_locator)
        self.assertEqual(logs, [])
        self.assertGreaterEqual(len(page.wait_calls), 8)

    def test_wait_for_url_contains_returns_when_keyword_appears(self):
        page = FakePage()
        urls = ["https://mp.weixin.qq.com/", "https://mp.weixin.qq.com/wxamp/index/index?token=1"]

        def fake_wait(_timeout):
            page.wait_calls.append(_timeout)
            if len(urls) > 1:
                page.url = urls.pop(1)

        page.url = urls[0]
        page.wait_for_timeout = fake_wait

        self.assertTrue(wait_for_url_contains(page, ("token=",)))

    def test_wait_for_current_account_name_returns_expected_name(self):
        page = FakePage()
        names = ["", "目标账号"]

        with patch(
            "desktop_py.core.fetcher.extract_current_account_name",
            side_effect=lambda _page: names.pop(0) if len(names) > 1 else names[0],
        ):
            actual_name = wait_for_current_account_name(page, "目标账号", timeout_ms=1000)

        self.assertEqual(actual_name, "目标账号")

    def test_wait_for_account_switch_stable_requires_repeated_match(self):
        page = FakePage()
        page.url = "https://mp.weixin.qq.com/wxamp/index/index?token=1"
        names = iter(["目标账号", "目标账号"])

        actual_name = wait_for_account_switch_stable(
            page,
            "目标账号",
            extract_current_account_name_fn=lambda _page: next(names),
            wait_for_url_contains_fn=lambda *_args, **_kwargs: True,
            wait_or_cancel_fn=lambda _page, timeout_ms, _is_cancelled=None: page.wait_for_timeout(timeout_ms),
            stable_rounds=2,
            interval_ms=1,
        )

        self.assertEqual(actual_name, "目标账号")
        self.assertEqual(page.wait_calls, [1])

    def test_wait_for_account_switch_stable_raises_on_wrong_account(self):
        page = FakePage()
        page.url = "https://mp.weixin.qq.com/wxamp/index/index?token=1"

        with self.assertRaisesRegex(Exception, "不是目标账号"):
            wait_for_account_switch_stable(
                page,
                "目标账号",
                extract_current_account_name_fn=lambda _page: "其他账号",
                wait_for_url_contains_fn=lambda *_args, **_kwargs: True,
                wait_or_cancel_fn=lambda _page, timeout_ms, _is_cancelled=None: None,
                stable_rounds=2,
                interval_ms=1,
            )

    def test_prepare_switch_account_page_recovers_login_timeout_screen(self):
        class TimeoutPage:
            def __init__(self):
                self.url = "https://mp.weixin.qq.com/"
                self.recovered = False
                self.goto_calls: list[str] = []

            def wait_for_load_state(self, state=None, timeout=None):
                return None

            def wait_for_timeout(self, timeout):
                return None

            def get_by_text(self, text, exact=False):
                if text == "切换账号" and self.recovered:
                    return FakeLocator(count=1)
                return FakeLocator()

            def locator(self, selector, **kwargs):
                has_text = kwargs.get("has_text")
                if selector == "text=登录超时，请重新登录":
                    return FakeLocator(count=0 if self.recovered else 1)
                if selector == "text=小程序":
                    return FakeLocator(count=1, click_cb=self._recover)
                if selector == "text=退出登录":
                    return FakeLocator(count=1)
                if selector == "div.menu_box_account_info_item[title='切换账号']":
                    return FakeLocator(count=1 if self.recovered else 0)
                if selector == ".menu_box_account_info_item" and has_text == "切换账号":
                    return FakeLocator(count=1 if self.recovered else 0)
                if selector == "[title='切换账号']":
                    return FakeLocator(count=1 if self.recovered else 0)
                if selector == ".switch_account_dialog":
                    return FakeLocator(count=0)
                if selector == ".switch_account_dialog .account_item":
                    return FakeLocator(count=0)
                return FakeLocator()

            def content(self):
                if self.recovered:
                    return '<div class="menu_box_account_info_item" title="切换账号">切换账号</div>'
                return "<div>登录超时，请重新登录</div><div>小程序</div><div>退出登录</div>"

            def goto(self, url, wait_until=None, timeout=None):
                self.goto_calls.append(url)
                self.url = url

            def _recover(self):
                self.recovered = True
                self.url = "https://mp.weixin.qq.com/wxamp/index/index?token=1"

        page = TimeoutPage()
        prepare_switch_account_page(
            page,
            "https://mp.weixin.qq.com/",
            None,
            switch_dialog_ready_fn=lambda _page: False,
            find_switch_entry_fn=find_switch_entry,
            should_retry_switch_from_home_fn=should_retry_switch_from_home,
            log_fn=lambda *_args, **_kwargs: None,
            wait_for_url_contains_fn=lambda *_args, **_kwargs: True,
        )

        self.assertTrue(page.recovered)
        self.assertEqual(page.goto_calls, [])

    def test_prepare_switch_account_page_recovers_root_page_before_switch_lookup(self):
        logs: list[str] = []
        waited_keywords: list[tuple[str, ...]] = []

        class RootPage:
            def __init__(self):
                self.url = "https://mp.weixin.qq.com/"
                self.recovered = False
                self.goto_calls: list[str] = []

            def wait_for_load_state(self, state=None, timeout=None):
                return None

            def wait_for_timeout(self, timeout):
                return None

            def get_by_text(self, text, exact=False):
                if text == "切换账号" and self.recovered:
                    return FakeLocator(count=1)
                return FakeLocator()

            def locator(self, selector, **kwargs):
                has_text = kwargs.get("has_text")
                if selector in {
                    "div:has-text('小程序')",
                    "span:has-text('小程序')",
                    "a:has-text('小程序')",
                    "text=小程序",
                }:
                    return FakeLocator(count=0 if self.recovered else 1, click_cb=self._recover)
                if selector == "div.menu_box_account_info_item[title='切换账号']":
                    return FakeLocator(count=1 if self.recovered else 0)
                if selector == ".menu_box_account_info_item" and has_text == "切换账号":
                    return FakeLocator(count=1 if self.recovered else 0)
                if selector == "[title='切换账号']":
                    return FakeLocator(count=1 if self.recovered else 0)
                if selector in {
                    ".switch_account_dialog",
                    ".switch_account_dialog .account_item",
                    "text=登录超时，请重新登录",
                    "text=登录超时",
                    "text=请重新登录",
                    "text=退出登录",
                }:
                    return FakeLocator()
                return FakeLocator()

            def content(self):
                if self.recovered:
                    return '<div class="menu_box_account_info_item" title="切换账号">切换账号</div>'
                return "<div>小程序</div>"

            def goto(self, url, wait_until=None, timeout=None):
                self.goto_calls.append(url)
                self.url = url

            def _recover(self):
                self.recovered = True
                self.url = "https://mp.weixin.qq.com/wxamp/index/index?token=1"

        page = RootPage()
        prepare_switch_account_page(
            page,
            "https://mp.weixin.qq.com/",
            logs.append,
            switch_dialog_ready_fn=lambda _page: False,
            find_switch_entry_fn=find_switch_entry,
            should_retry_switch_from_home_fn=should_retry_switch_from_home,
            log_fn=lambda logger, message: logger(message),
            wait_for_url_contains_fn=lambda _page, keywords, **_kwargs: waited_keywords.append(keywords) or True,
        )

        self.assertTrue(page.recovered)
        self.assertEqual(page.goto_calls, [])
        self.assertIn(("token=", "/wxamp/index/index"), waited_keywords)
        self.assertIn("微信后台根页恢复成功。", logs)

    def test_prepare_switch_account_page_falls_back_to_feedback_url_when_root_recovery_stays_on_root(self):
        logs: list[str] = []

        class RootPage:
            def __init__(self):
                self.url = "https://mp.weixin.qq.com/"
                self.recovered = False
                self.goto_calls: list[str] = []

            def wait_for_load_state(self, state=None, timeout=None):
                return None

            def wait_for_timeout(self, timeout):
                return None

            def get_by_text(self, text, exact=False):
                if text == "切换账号" and self.recovered:
                    return FakeLocator(count=1)
                return FakeLocator()

            def locator(self, selector, **kwargs):
                has_text = kwargs.get("has_text")
                if selector in {
                    "div:has-text('小程序')",
                    "span:has-text('小程序')",
                    "a:has-text('小程序')",
                    "text=小程序",
                }:
                    return FakeLocator(count=1)
                if selector == "div.menu_box_account_info_item[title='切换账号']":
                    return FakeLocator(count=1 if self.recovered else 0)
                if selector == ".menu_box_account_info_item" and has_text == "切换账号":
                    return FakeLocator(count=1 if self.recovered else 0)
                if selector == "[title='切换账号']":
                    return FakeLocator(count=1 if self.recovered else 0)
                if selector in {
                    ".switch_account_dialog",
                    ".switch_account_dialog .account_item",
                    "text=登录超时，请重新登录",
                    "text=登录超时",
                    "text=请重新登录",
                    "text=退出登录",
                }:
                    return FakeLocator()
                return FakeLocator()

            def content(self):
                if self.recovered:
                    return '<div class="menu_box_account_info_item" title="切换账号">切换账号</div>'
                return "<div>小程序</div>"

            def goto(self, url, wait_until=None, timeout=None):
                self.goto_calls.append(url)
                self.url = url
                self.recovered = "pluginRedirect/gameFeedback" in url

        feedback_url = "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=321"
        page = RootPage()
        prepare_switch_account_page(
            page,
            "https://mp.weixin.qq.com/",
            logs.append,
            fallback_url=feedback_url,
            switch_dialog_ready_fn=lambda _page: False,
            find_switch_entry_fn=find_switch_entry,
            should_retry_switch_from_home_fn=should_retry_switch_from_home,
            log_fn=lambda logger, message: logger(message),
            wait_for_url_contains_fn=lambda *_args, **_kwargs: True,
        )

        self.assertEqual(
            page.goto_calls,
            [
                "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?action=plugin_redirect&plugin_uin=1010&selected=2&token=321&lang=zh_CN"
            ],
        )
        self.assertIn("微信后台根页恢复失败：点击“小程序”后仍停留在根页。", logs)
        self.assertTrue(any("正在打开历史反馈页重试" in message for message in logs))
