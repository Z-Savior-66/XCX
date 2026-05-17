from desktop_py.core.fetcher_session import _select_renew_switch_account_name
from py_tests.fetcher_test_support import (
    AccountConfig,
    FakeLocator,
    FetcherTestBase,
    Path,
    PlaywrightTimeoutError,
    TemporaryDirectory,
    _close_context_and_browser,
    analyze_storage_state,
    asyncio,
    fetch_switchable_accounts,
    json,
    patch,
    persist_storage_state,
    renew_account_state,
    save_login_state,
    save_login_state_with_profile,
    validate_account_state,
)


class FetcherSessionTestCase(FetcherTestBase):
    def write_fake_storage_state(self, path: str | Path | None) -> None:
        assert path is not None
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "cookies": [
                        {
                            "name": "session",
                            "value": "x",
                            "domain": "mp.weixin.qq.com",
                            "path": "/",
                            "expires": -1,
                        }
                    ],
                    "origins": [],
                }
            ),
            encoding="utf-8",
        )

    def test_select_renew_switch_account_name_rotates_all_candidates_before_repeating(self):
        names = ["导入账号A", "导入账号B", "导入账号C"]

        self.assertEqual(
            _select_renew_switch_account_name(
                names,
                current_account_name="导入账号A",
                previous_account_name="导入账号C",
            ),
            "导入账号B",
        )
        self.assertEqual(
            _select_renew_switch_account_name(
                names,
                current_account_name="导入账号B",
                previous_account_name="导入账号A",
            ),
            "导入账号C",
        )
        self.assertEqual(
            _select_renew_switch_account_name(
                names,
                current_account_name="导入账号C",
                previous_account_name="导入账号B",
            ),
            "导入账号A",
        )

    def test_select_renew_switch_account_name_does_not_repeat_single_current_account(self):
        self.assertEqual(
            _select_renew_switch_account_name(
                ["导入账号A"],
                current_account_name="导入账号A",
                previous_account_name="导入账号C",
            ),
            "",
        )

    def test_analyze_storage_state_reports_missing_file(self):
        report = analyze_storage_state("storage/not-exists.json")

        self.assertFalse(report.exists)
        self.assertFalse(report.readable)
        self.assertIn("不存在", report.reason)

    def test_analyze_storage_state_reports_expiring_weixin_cookie(self):
        with TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "cookies": [
                            {
                                "name": "session",
                                "value": "x",
                                "domain": ".mp.weixin.qq.com",
                                "path": "/",
                                "expires": 1300,
                            },
                            {
                                "name": "other",
                                "value": "y",
                                "domain": "example.com",
                                "path": "/",
                                "expires": 9999,
                            },
                        ],
                        "origins": [
                            {
                                "origin": "https://mp.weixin.qq.com",
                                "localStorage": [],
                                "indexedDB": [{"name": "db"}],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            report = analyze_storage_state(str(state_path), now_seconds=1000)

        self.assertTrue(report.exists)
        self.assertTrue(report.readable)
        self.assertTrue(report.has_reusable_state)
        self.assertTrue(report.has_indexed_db)
        self.assertEqual(report.cookies_count, 2)
        self.assertEqual(report.origins_count, 1)
        self.assertEqual(report.matched_cookies_count, 1)
        self.assertEqual(report.min_cookie_seconds_remaining, 300)

    def test_analyze_storage_state_reports_expired_weixin_cookie(self):
        with TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "cookies": [
                            {
                                "name": "session",
                                "value": "x",
                                "domain": "mp.weixin.qq.com",
                                "path": "/",
                                "expires": 900,
                            }
                        ],
                        "origins": [],
                    }
                ),
                encoding="utf-8",
            )

            report = analyze_storage_state(str(state_path), now_seconds=1000)

        self.assertEqual(report.expired_cookies_count, 1)
        self.assertEqual(report.min_cookie_seconds_remaining, -100)
        self.assertIn("已过期", report.reason)

    def test_analyze_storage_state_counts_session_cookie_without_expires(self):
        with TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "cookies": [
                            {
                                "name": "session",
                                "value": "x",
                                "domain": "mp.weixin.qq.com",
                                "path": "/",
                                "expires": -1,
                            }
                        ],
                        "origins": [],
                    }
                ),
                encoding="utf-8",
            )

            report = analyze_storage_state(str(state_path), now_seconds=1000)

        self.assertEqual(report.session_cookies_count, 1)
        self.assertIsNone(report.min_cookie_seconds_remaining)
        self.assertIn("会话 Cookie", report.reason)

    def test_analyze_storage_state_reports_state_without_weixin_cookie(self):
        with TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "cookies": [
                            {
                                "name": "session",
                                "value": "x",
                                "domain": "example.com",
                                "path": "/",
                                "expires": 1300,
                            }
                        ],
                        "origins": [],
                    }
                ),
                encoding="utf-8",
            )

            report = analyze_storage_state(str(state_path), now_seconds=1000)

        self.assertEqual(report.cookies_count, 1)
        self.assertEqual(report.matched_cookies_count, 0)
        self.assertIn("未找到微信后台相关 Cookie", report.reason)

    def test_persist_storage_state_falls_back_when_indexed_db_export_keeps_failing(self):
        calls: list[str] = []
        logs: list[str] = []

        class FakeContext:
            def storage_state(self, path=None, indexed_db=False):
                calls.append(f"storage:{Path(path).name}:{indexed_db}")
                if indexed_db:
                    raise RuntimeError("Unable to serialize IndexedDB: Internal error.")
                Path(path).write_text('{"cookies":[],"origins":[]}', encoding="utf-8")

        class FakePageForStorage:
            def wait_for_load_state(self, state=None, timeout=None):
                calls.append(f"load:{state}:{timeout}")

            def wait_for_timeout(self, timeout):
                calls.append(f"wait:{timeout}")

            def is_closed(self):
                return False

        with TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "state.json"
            result = persist_storage_state(
                FakeContext(),
                str(target),
                page=FakePageForStorage(),
                logger=logs.append,
                log_fn=lambda logger, message: logger(message),
                retry_delays_ms=(1, 2),
                fallback_verify_fn=lambda temp_path: Path(temp_path).exists(),
            )

            self.assertTrue(target.exists())

        self.assertFalse(result.indexed_db)
        self.assertTrue(result.fallback_verified)
        self.assertEqual(result.attempts, 3)
        self.assertEqual(calls.count("storage:state.json:True"), 3)
        self.assertIn("storage:.state.json.fallback.tmp:False", calls)
        self.assertIn("降级登录态已通过复验并保存。", logs[-1])

    def test_persist_storage_state_keeps_original_when_fallback_verification_fails(self):
        class FakeContext:
            def storage_state(self, path=None, indexed_db=False):
                if indexed_db:
                    raise RuntimeError("Unable to serialize IndexedDB: Internal error.")
                Path(path).write_text('{"cookies":[],"origins":[]}', encoding="utf-8")

        with TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "state.json"
            target.write_text("original", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "Unable to serialize IndexedDB"):
                persist_storage_state(
                    FakeContext(),
                    str(target),
                    retry_delays_ms=(),
                    fallback_verify_fn=lambda _temp_path: False,
                )

            self.assertEqual(target.read_text(encoding="utf-8"), "original")

    def test_close_context_and_browser_still_closes_browser_when_context_close_fails(self):
        calls: list[str] = []

        class FakeContext:
            def close(self):
                calls.append("context")
                raise RuntimeError("context close failed")

        class FakeBrowser:
            def close(self):
                calls.append("browser")

        with self.assertRaisesRegex(RuntimeError, "context close failed"):
            _close_context_and_browser(FakeContext(), FakeBrowser())

        self.assertEqual(calls, ["context", "browser"])

    def test_save_login_state_still_closes_browser_when_context_close_fails(self):
        calls: list[str] = []

        class FakePageForLogin:
            def __init__(self):
                self.url = "https://mp.weixin.qq.com/wxamp/index/index?token=1"

            def goto(self, _url, wait_until=None):
                return None

            def wait_for_timeout(self, _timeout):
                return None

            def close(self):
                calls.append("page")

        class FakeContextForLogin:
            def __init__(self):
                self.page = FakePageForLogin()

            def new_page(self):
                return self.page

            def storage_state(self, path=None, indexed_db=False):
                return None

            def close(self):
                calls.append("context")
                raise RuntimeError("context close failed")

        class FakeBrowserForLogin:
            def __init__(self):
                self.context = FakeContextForLogin()

            def new_context(self, viewport=None):
                return self.context

            def close(self):
                calls.append("browser")

        fake_browser = FakeBrowserForLogin()
        fake_playwright = type(
            "FakePlaywright",
            (),
            {"chromium": type("FakeChromium", (), {"launch": lambda self, headless=False: fake_browser})()},
        )()

        with patch("desktop_py.core.fetcher.sync_playwright") as mock_playwright:
            mock_playwright.return_value.__enter__.return_value = fake_playwright
            with self.assertRaisesRegex(RuntimeError, "context close failed"):
                save_login_state(AccountConfig(name="账号A", state_path="storage/a.json"), 1)

        self.assertEqual(calls, ["page", "context", "browser"])

    def test_save_login_state_fails_without_overwriting_existing_state_when_login_not_completed(self):
        calls: list[str] = []

        class FakePageForLogin:
            def __init__(self):
                self.url = "https://mp.weixin.qq.com/"

            def goto(self, _url, wait_until=None):
                return None

            def wait_for_timeout(self, _timeout):
                return None

            def close(self):
                calls.append("page")

        class FakeContextForLogin:
            def __init__(self):
                self.page = FakePageForLogin()

            def new_page(self):
                return self.page

            def storage_state(self, path=None, indexed_db=False):
                calls.append(f"storage:{path}:{indexed_db}")

            def close(self):
                calls.append("context")

        class FakeBrowserForLogin:
            def __init__(self):
                self.context = FakeContextForLogin()

            def new_context(self, viewport=None):
                return self.context

            def close(self):
                calls.append("browser")

        fake_browser = FakeBrowserForLogin()
        fake_playwright = type(
            "FakePlaywright",
            (),
            {"chromium": type("FakeChromium", (), {"launch": lambda self, headless=False: fake_browser})()},
        )()

        timestamps = iter([100.0, 101.0])
        with (
            patch("desktop_py.core.fetcher.sync_playwright") as mock_playwright,
            patch("desktop_py.core.fetcher.datetime") as mock_datetime,
        ):
            mock_playwright.return_value.__enter__.return_value = fake_playwright
            mock_datetime.now.return_value.timestamp.side_effect = lambda: next(timestamps)

            with self.assertRaisesRegex(Exception, "未在限定时间内检测到登录成功"):
                save_login_state(AccountConfig(name="账号A", state_path="storage/a.json"), 1)

        self.assertEqual(calls, ["page", "context", "browser"])
        self.assertFalse(any(call.startswith("storage:") for call in calls))

    def test_save_login_state_refreshes_feedback_url_from_backend_home_url(self):
        class FakePageForLogin:
            def __init__(self):
                self.url = "https://mp.weixin.qq.com/"

            def goto(self, _url, wait_until=None):
                return None

            def wait_for_timeout(self, _timeout):
                self.url = "https://mp.weixin.qq.com/wxamp/index/index?token=321"

            def close(self):
                return None

        class FakeContextForLogin:
            def __init__(self):
                self.page = FakePageForLogin()

            def new_page(self):
                return self.page

            def storage_state(self, path=None, indexed_db=False):
                return None

            def close(self):
                return None

        class FakeBrowserForLogin:
            def __init__(self):
                self.context = FakeContextForLogin()

            def new_context(self, viewport=None):
                return self.context

            def close(self):
                return None

        fake_browser = FakeBrowserForLogin()
        fake_playwright = type(
            "FakePlaywright",
            (),
            {"chromium": type("FakeChromium", (), {"launch": lambda self, headless=False: fake_browser})()},
        )()
        account = AccountConfig(name="账号A", state_path="storage/a.json")
        timestamps = iter([100.0, 100.5])

        with (
            patch("desktop_py.core.fetcher.sync_playwright") as mock_playwright,
            patch("desktop_py.core.fetcher.datetime") as mock_datetime,
        ):
            mock_playwright.return_value.__enter__.return_value = fake_playwright
            mock_datetime.now.return_value.timestamp.side_effect = lambda: next(timestamps)

            save_login_state(account, 2)

        self.assertEqual(
            account.feedback_url,
            "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?action=plugin_redirect&plugin_uin=1010&selected=2&token=321&lang=zh_CN",
        )

    def test_fetch_switchable_accounts_still_closes_browser_when_context_close_fails(self):
        calls: list[str] = []

        class FakePageForSwitch:
            def goto(self, _url, wait_until=None, timeout=None):
                return None

            def close(self):
                calls.append("page")

        class FakeContextForSwitch:
            def __init__(self):
                self.page = FakePageForSwitch()

            def new_page(self):
                return self.page

            def close(self):
                calls.append("context")
                raise RuntimeError("context close failed")

        class FakeBrowserForSwitch:
            def close(self):
                calls.append("browser")

        with (
            patch("desktop_py.core.fetcher.sync_playwright") as mock_playwright,
            patch(
                "desktop_py.core.fetcher.create_browser_context",
                return_value=(FakeBrowserForSwitch(), FakeContextForSwitch()),
            ),
            patch("desktop_py.core.fetcher.wait_for_url_contains", return_value=True),
            patch("desktop_py.core.fetcher.list_switchable_accounts", return_value=["账号A", "账号B"]),
            patch("desktop_py.core.fetcher.Path.exists", return_value=True),
        ):
            mock_playwright.return_value.__enter__.return_value = object()
            with self.assertRaisesRegex(RuntimeError, "context close failed"):
                fetch_switchable_accounts(
                    AccountConfig(name="主账号", state_path="storage/shared.json"), profile_dir=""
                )

        self.assertEqual(calls, ["page", "context", "browser"])

    def test_fetch_switchable_accounts_uses_home_url_instead_of_stale_feedback_url(self):
        calls: list[str] = []

        class FakePageForSwitch:
            def goto(self, url, wait_until=None, timeout=None):
                calls.append(f"goto:{url}")

            def close(self):
                calls.append("page")

        class FakeContextForSwitch:
            def __init__(self):
                self.page = FakePageForSwitch()

            def new_page(self):
                return self.page

            def close(self):
                calls.append("context")

        account = AccountConfig(
            name="主账号",
            state_path="storage/shared.json",
            home_url="https://mp.weixin.qq.com/",
            feedback_url="https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=old",
        )

        with (
            patch("desktop_py.core.fetcher.sync_playwright") as mock_playwright,
            patch("desktop_py.core.fetcher.create_browser_context", return_value=(None, FakeContextForSwitch())),
            patch("desktop_py.core.fetcher.wait_for_url_contains", return_value=True),
            patch("desktop_py.core.fetcher.list_switchable_accounts", return_value=["账号A"]),
            patch("desktop_py.core.fetcher.Path.exists", return_value=True),
        ):
            mock_playwright.return_value.__enter__.return_value = object()

            names = fetch_switchable_accounts(account)

        self.assertEqual(names, ["账号A"])
        self.assertEqual(calls[0], "goto:https://mp.weixin.qq.com/")

    def test_validate_account_state_does_not_persist_shared_profile_state(self):
        calls: list[str] = []

        class FakePageForValidation:
            url = "https://mp.weixin.qq.com/wxamp/index/index?token=1"

            def goto(self, _url, wait_until=None, timeout=None):
                calls.append("goto")

            def close(self):
                calls.append("page")

        class FakeContextForValidation:
            def __init__(self):
                self.page = FakePageForValidation()

            def new_page(self):
                return self.page

            def storage_state(self, path=None, indexed_db=False):
                calls.append(f"storage:{path}:{indexed_db}")

            def close(self):
                calls.append("context")

        with (
            patch("desktop_py.core.fetcher.sync_playwright") as mock_playwright,
            patch(
                "desktop_py.core.fetcher.create_browser_context",
                return_value=(None, FakeContextForValidation()),
            ),
            patch("desktop_py.core.fetcher.validate_shared_browser_profile_dir", return_value="C:/profile"),
            patch("desktop_py.core.fetcher.wait_for_url_contains", return_value=True),
        ):
            mock_playwright.return_value.__enter__.return_value = object()

            valid = validate_account_state(
                AccountConfig(name="主账号", state_path="storage/shared.json"),
                profile_dir="C:/profile",
            )

        self.assertTrue(valid)
        self.assertNotIn("storage:storage\\shared.json:True", calls)
        self.assertEqual(calls[-2:], ["page", "context"])

    def test_validate_account_state_rejects_transient_backend_url_match_without_page_signals(self):
        calls: list[str] = []

        class FakePageForValidation:
            url = "https://mp.weixin.qq.com/"

            def goto(self, _url, wait_until=None, timeout=None):
                calls.append("goto")

            def content(self):
                return "<html></html>"

            def locator(self, selector, **kwargs):
                return FakeLocator()

            def get_by_text(self, text, exact=False):
                return FakeLocator()

            def close(self):
                calls.append("page")

        class FakeContextForValidation:
            def __init__(self):
                self.page = FakePageForValidation()

            def new_page(self):
                return self.page

            def close(self):
                calls.append("context")

        with (
            patch("desktop_py.core.fetcher.sync_playwright") as mock_playwright,
            patch(
                "desktop_py.core.fetcher.create_browser_context",
                return_value=(None, FakeContextForValidation()),
            ),
            patch("desktop_py.core.fetcher.Path.exists", return_value=True),
            patch("desktop_py.core.fetcher.wait_for_url_contains", return_value=True) as mock_wait,
        ):
            mock_playwright.return_value.__enter__.return_value = object()

            valid = validate_account_state(AccountConfig(name="主账号", state_path="storage/shared.json"))

        self.assertFalse(valid)
        mock_wait.assert_called_once_with(
            mock_wait.call_args.args[0],
            ("token=", "/wxamp/index/index", "pluginRedirect/gameFeedback"),
            timeout_ms=10000,
        )
        self.assertEqual(calls[-2:], ["page", "context"])

    def test_validate_account_state_accepts_feedback_page_url(self):
        class FakePageForValidation:
            url = "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?action=plugin_redirect&token=1"

            def goto(self, _url, wait_until=None, timeout=None):
                return None

            def close(self):
                return None

        class FakeContextForValidation:
            def __init__(self):
                self.page = FakePageForValidation()

            def new_page(self):
                return self.page

            def close(self):
                return None

        with (
            patch("desktop_py.core.fetcher.sync_playwright") as mock_playwright,
            patch(
                "desktop_py.core.fetcher.create_browser_context",
                return_value=(None, FakeContextForValidation()),
            ),
            patch("desktop_py.core.fetcher.Path.exists", return_value=True),
            patch("desktop_py.core.fetcher.wait_for_url_contains", return_value=False),
        ):
            mock_playwright.return_value.__enter__.return_value = object()

            valid = validate_account_state(AccountConfig(name="主账号", state_path="storage/shared.json"))

        self.assertTrue(valid)

    def test_validate_account_state_refreshes_feedback_url_from_backend_home_url(self):
        account = AccountConfig(name="主账号", state_path="storage/shared.json")

        class FakePageForValidation:
            url = "https://mp.weixin.qq.com/wxamp/index/index?token=123"

            def goto(self, _url, wait_until=None, timeout=None):
                return None

            def close(self):
                return None

        class FakeContextForValidation:
            def __init__(self):
                self.page = FakePageForValidation()

            def new_page(self):
                return self.page

            def close(self):
                return None

        with (
            patch("desktop_py.core.fetcher.sync_playwright") as mock_playwright,
            patch(
                "desktop_py.core.fetcher.create_browser_context",
                return_value=(None, FakeContextForValidation()),
            ),
            patch("desktop_py.core.fetcher.Path.exists", return_value=True),
            patch("desktop_py.core.fetcher.wait_for_url_contains", return_value=True),
        ):
            mock_playwright.return_value.__enter__.return_value = object()

            valid = validate_account_state(account)

        self.assertTrue(valid)
        self.assertEqual(
            account.feedback_url,
            "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?action=plugin_redirect&plugin_uin=1010&selected=2&token=123&lang=zh_CN",
        )

    def test_renew_account_state_persists_shared_profile_state(self):
        calls: list[str] = []
        write_state = self.write_fake_storage_state

        class FakePageForValidation:
            url = "https://mp.weixin.qq.com/wxamp/index/index?token=1"

            def goto(self, _url, wait_until=None, timeout=None):
                calls.append("goto")

            def close(self):
                calls.append("page")

        class FakeContextForValidation:
            def __init__(self):
                self.page = FakePageForValidation()

            def new_page(self):
                return self.page

            def storage_state(self, path=None, indexed_db=False):
                calls.append(f"storage:{path}:{indexed_db}")
                write_state(path)

            def close(self):
                calls.append("context")

        with TemporaryDirectory() as temp_dir:
            state_path = str(Path(temp_dir) / "shared.json")
            Path(state_path).write_text("original", encoding="utf-8")
            with (
                patch("desktop_py.core.fetcher.sync_playwright") as mock_playwright,
                patch(
                    "desktop_py.core.fetcher.create_browser_context",
                    return_value=(None, FakeContextForValidation()),
                ),
                patch("desktop_py.core.fetcher.validate_shared_browser_profile_dir", return_value="C:/profile"),
                patch("desktop_py.core.fetcher.wait_for_url_contains", return_value=True),
            ):
                mock_playwright.return_value.__enter__.return_value = object()

                valid = renew_account_state(
                    AccountConfig(name="主账号", state_path=state_path),
                    profile_dir="C:/profile",
                )

        self.assertTrue(valid)
        self.assertTrue(any(".renew.tmp" in call for call in calls if call.startswith("storage:")))
        self.assertGreaterEqual(calls.count("context"), 2)

    def test_renew_account_state_refreshes_feedback_url_from_backend_home_url(self):
        account = AccountConfig(name="主账号", state_path="storage/shared.json")
        write_state = self.write_fake_storage_state

        class FakePageForRenew:
            url = "https://mp.weixin.qq.com/wxamp/index/index?token=456"

            def goto(self, _url, wait_until=None, timeout=None):
                return None

            def close(self):
                return None

        class FakeContextForRenew:
            def __init__(self):
                self.page = FakePageForRenew()

            def new_page(self):
                return self.page

            def storage_state(self, path=None, indexed_db=False):
                write_state(path)
                return None

            def close(self):
                return None

        with TemporaryDirectory() as temp_dir:
            account.state_path = str(Path(temp_dir) / "shared.json")
            Path(account.state_path).write_text("original", encoding="utf-8")
            with (
                patch("desktop_py.core.fetcher.sync_playwright") as mock_playwright,
                patch(
                    "desktop_py.core.fetcher.create_browser_context",
                    return_value=(None, FakeContextForRenew()),
                ),
                patch("desktop_py.core.fetcher.wait_for_url_contains", return_value=True),
            ):
                mock_playwright.return_value.__enter__.return_value = object()

                valid = renew_account_state(account)

        self.assertTrue(valid)
        self.assertEqual(
            account.feedback_url,
            "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?action=plugin_redirect&plugin_uin=1010&selected=2&token=456&lang=zh_CN",
        )

    def test_renew_account_state_passes_headless_flag_to_browser_context(self):
        observed: list[object] = []
        write_state = self.write_fake_storage_state

        class FakePageForRenew:
            url = "https://mp.weixin.qq.com/wxamp/index/index?token=1"

            def goto(self, _url, wait_until=None, timeout=None):
                return None

            def close(self):
                return None

        class FakeContextForRenew:
            def __init__(self):
                self.page = FakePageForRenew()

            def new_page(self):
                return self.page

            def storage_state(self, path=None, indexed_db=False):
                write_state(path)
                return None

            def close(self):
                return None

        def fake_create_browser_context(_playwright, account, headless, profile_dir):
            observed.extend([account.name, headless, profile_dir])
            return None, FakeContextForRenew()

        with TemporaryDirectory() as temp_dir:
            state_path = str(Path(temp_dir) / "shared.json")
            Path(state_path).write_text("original", encoding="utf-8")
            with (
                patch("desktop_py.core.fetcher.sync_playwright") as mock_playwright,
                patch("desktop_py.core.fetcher.create_browser_context", side_effect=fake_create_browser_context),
                patch("desktop_py.core.fetcher.validate_shared_browser_profile_dir", return_value="C:/profile"),
                patch("desktop_py.core.fetcher.wait_for_url_contains", return_value=True),
            ):
                mock_playwright.return_value.__enter__.return_value = object()

                valid = renew_account_state(
                    AccountConfig(name="accountA", state_path=state_path),
                    profile_dir="C:/profile",
                    headless=False,
                )

        self.assertTrue(valid)
        self.assertEqual(observed, ["accountA", False, "C:/profile", "accountA", False, ""])

    def test_renew_account_state_persists_regular_state_file(self):
        calls: list[str] = []
        write_state = self.write_fake_storage_state

        class FakePageForRenew:
            url = "https://mp.weixin.qq.com/wxamp/index/index?token=1"

            def goto(self, _url, wait_until=None, timeout=None):
                calls.append("goto")

            def close(self):
                calls.append("page")

        class FakeContextForRenew:
            def __init__(self):
                self.page = FakePageForRenew()

            def new_page(self):
                return self.page

            def storage_state(self, path=None, indexed_db=False):
                calls.append(f"storage:{path}:{indexed_db}")
                write_state(path)

            def close(self):
                calls.append("context")

        fake_browser = type("FakeBrowser", (), {"close": lambda self: calls.append("browser")})()

        with TemporaryDirectory() as temp_dir:
            state_path = str(Path(temp_dir) / "shared.json")
            Path(state_path).write_text("original", encoding="utf-8")
            with (
                patch("desktop_py.core.fetcher.sync_playwright") as mock_playwright,
                patch(
                    "desktop_py.core.fetcher.create_browser_context",
                    return_value=(fake_browser, FakeContextForRenew()),
                ),
                patch("desktop_py.core.fetcher.wait_for_url_contains", return_value=True),
            ):
                mock_playwright.return_value.__enter__.return_value = object()

                valid = renew_account_state(
                    AccountConfig(name="主账号", state_path=state_path),
                    profile_dir="",
                )

        self.assertTrue(valid)
        self.assertTrue(any(".renew.tmp" in call for call in calls if call.startswith("storage:")))
        self.assertEqual(calls[-2:], ["context", "browser"])

    def test_renew_account_state_accepts_logged_in_backend_page_without_token_url(self):
        calls: list[str] = []
        write_state = self.write_fake_storage_state

        class FakePageForRenew:
            url = "https://mp.weixin.qq.com/"

            def goto(self, _url, wait_until=None, timeout=None):
                calls.append(f"goto:{_url}")

            def wait_for_load_state(self, _state, timeout=None):
                return None

            def content(self):
                return '<div class="menu_box_account_info_item">退出登录</div>'

            def close(self):
                calls.append("page")

        class FakeContextForRenew:
            def __init__(self):
                self.page = FakePageForRenew()

            def new_page(self):
                return self.page

            def storage_state(self, path=None, indexed_db=False):
                calls.append(f"storage:{path}:{indexed_db}")
                write_state(path)

            def close(self):
                calls.append("context")

        fake_browser = type("FakeBrowser", (), {"close": lambda self: calls.append("browser")})()

        with TemporaryDirectory() as temp_dir:
            state_path = str(Path(temp_dir) / "shared.json")
            Path(state_path).write_text("original", encoding="utf-8")
            with (
                patch("desktop_py.core.fetcher.sync_playwright") as mock_playwright,
                patch(
                    "desktop_py.core.fetcher.create_browser_context",
                    return_value=(fake_browser, FakeContextForRenew()),
                ),
                patch("desktop_py.core.fetcher.wait_for_url_contains", return_value=False),
            ):
                mock_playwright.return_value.__enter__.return_value = object()

                valid = renew_account_state(
                    AccountConfig(name="主账号", state_path=state_path),
                    profile_dir="",
                )

        self.assertTrue(valid)
        self.assertTrue(any(".renew.tmp" in call for call in calls if call.startswith("storage:")))

    def test_renew_account_state_recovers_login_timeout_page_via_mini_program_entry(self):
        calls: list[str] = []
        write_state = self.write_fake_storage_state

        class FakePageForRenew:
            def __init__(self):
                self.url = "https://mp.weixin.qq.com/"
                self.recovered = False

            def goto(self, url, wait_until=None, timeout=None):
                self.url = url
                calls.append(f"goto:{url}")

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
                    return '<div class="menu_box_account_info_item">账号设置</div>'
                return "<div>登录超时，请重新登录</div><div>小程序</div><div>退出登录</div>"

            def close(self):
                calls.append("page")

            def _recover(self):
                self.recovered = True
                self.url = "https://mp.weixin.qq.com/wxamp/index/index?token=1"
                calls.append("recover")

        class FakeContextForRenew:
            def __init__(self):
                self.page = FakePageForRenew()

            def new_page(self):
                return self.page

            def storage_state(self, path=None, indexed_db=False):
                calls.append(f"storage:{path}:{indexed_db}")
                write_state(path)

            def close(self):
                calls.append("context")

        fake_browser = type("FakeBrowser", (), {"close": lambda self: calls.append("browser")})()

        with TemporaryDirectory() as temp_dir:
            state_path = str(Path(temp_dir) / "shared.json")
            Path(state_path).write_text("original", encoding="utf-8")
            with (
                patch("desktop_py.core.fetcher.sync_playwright") as mock_playwright,
                patch(
                    "desktop_py.core.fetcher.create_browser_context",
                    return_value=(fake_browser, FakeContextForRenew()),
                ),
                patch(
                    "desktop_py.core.fetcher.wait_for_url_contains",
                    side_effect=lambda page, keywords, timeout_ms=0, is_cancelled=None: any(
                        keyword in page.url for keyword in keywords
                    ),
                ),
            ):
                mock_playwright.return_value.__enter__.return_value = object()

                valid = renew_account_state(
                    AccountConfig(name="主账号", state_path=state_path),
                    profile_dir="",
                )

        self.assertTrue(valid)
        self.assertIn("recover", calls)
        self.assertTrue(any(".renew.tmp" in call for call in calls if call.startswith("storage:")))

    def test_renew_account_state_keeps_original_when_saved_state_verification_fails(self):
        calls: list[str] = []
        write_state = self.write_fake_storage_state

        class ValidPageForRenew:
            url = "https://mp.weixin.qq.com/wxamp/index/index?token=1"

            def goto(self, _url, wait_until=None, timeout=None):
                calls.append("goto:renew")

            def close(self):
                calls.append("page:renew")

        class InvalidPageForVerify:
            url = "https://mp.weixin.qq.com/"

            def goto(self, _url, wait_until=None, timeout=None):
                calls.append("goto:verify")

            def locator(self, selector, **kwargs):
                return FakeLocator()

            def get_by_text(self, text, exact=False):
                return FakeLocator()

            def content(self):
                return "<html></html>"

            def close(self):
                calls.append("page:verify")

        class FakeContextForRenew:
            def __init__(self):
                self.page = ValidPageForRenew()

            def new_page(self):
                return self.page

            def storage_state(self, path=None, indexed_db=False):
                calls.append(f"storage:{path}:{indexed_db}")
                write_state(path)

            def close(self):
                calls.append("context:renew")

        class FakeContextForVerify:
            def __init__(self):
                self.page = InvalidPageForVerify()

            def new_page(self):
                return self.page

            def close(self):
                calls.append("context:verify")

        contexts = [FakeContextForRenew(), FakeContextForVerify()]

        def fake_create_browser_context(_playwright, _account, _headless, _profile_dir):
            return None, contexts.pop(0)

        with TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "shared.json"
            state_path.write_text("original", encoding="utf-8")
            account = AccountConfig(name="主账号", state_path=str(state_path))
            with (
                patch("desktop_py.core.fetcher.sync_playwright") as mock_playwright,
                patch("desktop_py.core.fetcher.create_browser_context", side_effect=fake_create_browser_context),
                patch("desktop_py.core.fetcher.wait_for_url_contains", return_value=True),
            ):
                mock_playwright.return_value.__enter__.return_value = object()

                valid = renew_account_state(account)

            self.assertEqual(state_path.read_text(encoding="utf-8"), "original")

        self.assertFalse(valid)
        self.assertIn("保存后复验失败", account.last_session_error)

    def test_renew_account_state_does_not_fall_back_to_saved_feedback_url(self):
        calls: list[str] = []

        class FakePageForRenew:
            url = "https://mp.weixin.qq.com/"

            def goto(self, url, wait_until=None, timeout=None):
                self.url = url
                calls.append(f"goto:{url}")

            def close(self):
                calls.append("page")

        class FakeContextForRenew:
            def __init__(self):
                self.page = FakePageForRenew()

            def new_page(self):
                return self.page

            def storage_state(self, path=None, indexed_db=False):
                calls.append(f"storage:{path}:{indexed_db}")

            def close(self):
                calls.append("context")

        fake_browser = type("FakeBrowser", (), {"close": lambda self: calls.append("browser")})()
        feedback_url = "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=current"

        with (
            patch("desktop_py.core.fetcher.sync_playwright") as mock_playwright,
            patch(
                "desktop_py.core.fetcher.create_browser_context",
                return_value=(fake_browser, FakeContextForRenew()),
            ),
            patch("desktop_py.core.fetcher.wait_for_url_contains", return_value=False),
            patch("desktop_py.core.fetcher.Path.exists", return_value=True),
        ):
            mock_playwright.return_value.__enter__.return_value = object()

            valid = renew_account_state(
                AccountConfig(name="主账号", state_path="storage/shared.json", feedback_url=feedback_url),
                profile_dir="",
            )

        self.assertFalse(valid)
        self.assertEqual(calls[:1], ["goto:https://mp.weixin.qq.com/"])
        self.assertFalse(any(call.startswith("storage:") for call in calls))

    def test_renew_account_state_fails_without_overwriting_when_home_timeout(self):
        calls: list[str] = []

        class FakePageForRenew:
            url = "https://mp.weixin.qq.com/"

            def goto(self, url, wait_until=None, timeout=None):
                calls.append(f"goto:{url}")
                if len(calls) == 1:
                    raise PlaywrightTimeoutError("home timeout")
                self.url = url

            def close(self):
                calls.append("page")

        class FakeContextForRenew:
            def __init__(self):
                self.page = FakePageForRenew()

            def new_page(self):
                return self.page

            def storage_state(self, path=None, indexed_db=False):
                calls.append(f"storage:{path}:{indexed_db}")

            def close(self):
                calls.append("context")

        fake_browser = type("FakeBrowser", (), {"close": lambda self: calls.append("browser")})()
        feedback_url = "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=current"

        with (
            patch("desktop_py.core.fetcher.sync_playwright") as mock_playwright,
            patch(
                "desktop_py.core.fetcher.create_browser_context",
                return_value=(fake_browser, FakeContextForRenew()),
            ),
            patch("desktop_py.core.fetcher.wait_for_url_contains", return_value=False),
            patch("desktop_py.core.fetcher.Path.exists", return_value=True),
        ):
            mock_playwright.return_value.__enter__.return_value = object()

            valid = renew_account_state(
                AccountConfig(name="主账号", state_path="storage/shared.json", feedback_url=feedback_url),
                profile_dir="",
            )

        self.assertFalse(valid)
        self.assertEqual(calls[:1], ["goto:https://mp.weixin.qq.com/"])
        self.assertFalse(any(call.startswith("storage:") for call in calls))

    def test_renew_account_state_does_not_overwrite_state_when_invalid(self):
        calls: list[str] = []

        class FakePageForRenew:
            url = "https://mp.weixin.qq.com/"

            def goto(self, _url, wait_until=None, timeout=None):
                calls.append("goto")

            def close(self):
                calls.append("page")

        class FakeContextForRenew:
            def __init__(self):
                self.page = FakePageForRenew()

            def new_page(self):
                return self.page

            def storage_state(self, path=None, indexed_db=False):
                calls.append(f"storage:{path}:{indexed_db}")

            def close(self):
                calls.append("context")

        fake_browser = type("FakeBrowser", (), {"close": lambda self: calls.append("browser")})()

        with (
            patch("desktop_py.core.fetcher.sync_playwright") as mock_playwright,
            patch(
                "desktop_py.core.fetcher.create_browser_context",
                return_value=(fake_browser, FakeContextForRenew()),
            ),
            patch("desktop_py.core.fetcher.wait_for_url_contains", side_effect=PlaywrightTimeoutError("timeout")),
            patch("desktop_py.core.fetcher.Path.exists", return_value=True),
        ):
            mock_playwright.return_value.__enter__.return_value = object()

            valid = renew_account_state(
                AccountConfig(name="主账号", state_path="storage/shared.json"),
                profile_dir="",
            )

        self.assertFalse(valid)
        self.assertFalse(any(call.startswith("storage:") for call in calls))

    def test_renew_account_state_logs_result(self):
        logs: list[str] = []
        write_state = self.write_fake_storage_state

        class FakePageForRenew:
            url = "https://mp.weixin.qq.com/wxamp/index/index?token=1"

            def goto(self, _url, wait_until=None, timeout=None):
                return None

            def close(self):
                return None

        class FakeContextForRenew:
            def __init__(self):
                self.page = FakePageForRenew()

            def new_page(self):
                return self.page

            def storage_state(self, path=None, indexed_db=False):
                write_state(path)
                return None

            def close(self):
                return None

        with TemporaryDirectory() as temp_dir:
            state_path = str(Path(temp_dir) / "shared.json")
            Path(state_path).write_text("original", encoding="utf-8")
            with (
                patch("desktop_py.core.fetcher.sync_playwright") as mock_playwright,
                patch(
                    "desktop_py.core.fetcher.create_browser_context",
                    return_value=(None, FakeContextForRenew()),
                ),
                patch("desktop_py.core.fetcher.validate_shared_browser_profile_dir", return_value="C:/profile"),
                patch("desktop_py.core.fetcher.wait_for_url_contains", return_value=True),
            ):
                mock_playwright.return_value.__enter__.return_value = object()
                valid = renew_account_state(
                    AccountConfig(name="主账号", state_path=state_path),
                    logger=logs.append,
                    profile_dir="C:/profile",
                )

        self.assertTrue(valid)
        self.assertIn("开始自动续期账号 主账号。", logs)
        self.assertIn("续期登录态已通过保存后复验并替换正式文件。", logs)
        self.assertIn("账号 主账号 自动续期成功。", logs)

    def test_renew_account_state_switches_to_different_candidate_after_valid_probe(self):
        calls: list[str] = []
        logs: list[str] = []
        write_state = self.write_fake_storage_state

        class FakePageForRenew:
            url = "https://mp.weixin.qq.com/wxamp/index/index?token=1"

            def goto(self, _url, wait_until=None, timeout=None):
                return None

            def close(self):
                calls.append("page")

        class FakeContextForRenew:
            def __init__(self):
                self.page = FakePageForRenew()

            def new_page(self):
                return self.page

            def storage_state(self, path=None, indexed_db=False):
                calls.append(f"storage:{path}:{indexed_db}")
                write_state(path)

            def close(self):
                calls.append("context")

        with TemporaryDirectory() as temp_dir:
            state_path = str(Path(temp_dir) / "shared.json")
            Path(state_path).write_text("original", encoding="utf-8")
            account = AccountConfig(
                name="主账号",
                state_path=state_path,
                last_actual_account_name="导入账号A",
            )
            with (
                patch("desktop_py.core.fetcher.sync_playwright") as mock_playwright,
                patch(
                    "desktop_py.core.fetcher.create_browser_context",
                    return_value=(None, FakeContextForRenew()),
                ),
                patch("desktop_py.core.fetcher.wait_for_url_contains", return_value=True),
                patch(
                    "desktop_py.core.fetcher.switch_to_account",
                    side_effect=lambda _page, name, _home_url, _logger: calls.append(f"switch:{name}"),
                ),
            ):
                mock_playwright.return_value.__enter__.return_value = object()
                valid = renew_account_state(
                    account,
                    logger=logs.append,
                    renew_switch_account_names=["导入账号A", "导入账号B"],
                )

        self.assertTrue(valid)
        self.assertIn("switch:导入账号B", calls)
        self.assertIn("自动续期准备切换到轮换账号：导入账号B。", logs)

    def test_renew_account_state_retries_with_visible_account_when_placeholder_is_missing(self):
        calls: list[str] = []
        logs: list[str] = []
        write_state = self.write_fake_storage_state

        class FakePageForRenew:
            url = "https://mp.weixin.qq.com/wxamp/index/index?token=1"

            def goto(self, _url, wait_until=None, timeout=None):
                return None

            def close(self):
                calls.append("page")

        class FakeContextForRenew:
            def __init__(self):
                self.page = FakePageForRenew()

            def new_page(self):
                return self.page

            def storage_state(self, path=None, indexed_db=False):
                calls.append(f"storage:{path}:{indexed_db}")
                write_state(path)

            def close(self):
                calls.append("context")

        def fake_switch_to_account(_page, name, _home_url, _logger):
            calls.append(f"switch:{name}")
            if name == "登录账号":
                raise RuntimeError("切换账号列表中未找到“登录账号”。当前可见账号：猎影、云梦伏妖录。")

        with TemporaryDirectory() as temp_dir:
            state_path = str(Path(temp_dir) / "shared.json")
            Path(state_path).write_text("original", encoding="utf-8")
            account = AccountConfig(name="登录账号", state_path=state_path)
            with (
                patch("desktop_py.core.fetcher.sync_playwright") as mock_playwright,
                patch(
                    "desktop_py.core.fetcher.create_browser_context",
                    return_value=(None, FakeContextForRenew()),
                ),
                patch("desktop_py.core.fetcher.wait_for_url_contains", return_value=True),
                patch("desktop_py.core.fetcher.switch_to_account", side_effect=fake_switch_to_account),
            ):
                mock_playwright.return_value.__enter__.return_value = object()
                valid = renew_account_state(
                    account,
                    logger=logs.append,
                    renew_switch_account_names=["登录账号"],
                )

        self.assertTrue(valid)
        self.assertEqual(calls[:2], ["switch:登录账号", "switch:猎影"])
        self.assertIn("自动续期轮换账号不可见，改为切换到当前可见账号：猎影。", logs)

    def test_validate_account_state_recovers_from_root_page_before_marking_offline(self):
        account = AccountConfig(name="主账号", state_path="storage/shared.json")

        class FakePageForValidation:
            def __init__(self):
                self.url = "https://mp.weixin.qq.com/"
                self.recovered = False

            def goto(self, _url, wait_until=None, timeout=None):
                return None

            def wait_for_timeout(self, timeout):
                return None

            def content(self):
                if self.recovered:
                    return '<div class="menu_box_account_info">账号设置</div><script>"nickName":"主账号"</script>'
                return "<html></html>"

            def locator(self, selector, **kwargs):
                if selector == "text=小程序":
                    return FakeLocator(count=1, click_cb=self._recover)
                if self.recovered and selector == "div.menu_box_account_info_item[title='切换账号']":
                    return FakeLocator(count=1)
                return FakeLocator()

            def get_by_text(self, text, exact=False):
                return FakeLocator()

            def close(self):
                return None

            def _recover(self):
                self.recovered = True
                self.url = "https://mp.weixin.qq.com/wxamp/index/index?token=1"

        class FakeContextForValidation:
            def __init__(self):
                self.page = FakePageForValidation()

            def new_page(self):
                return self.page

            def close(self):
                return None

        with (
            patch("desktop_py.core.fetcher.sync_playwright") as mock_playwright,
            patch("desktop_py.core.fetcher.create_browser_context", return_value=(None, FakeContextForValidation())),
            patch("desktop_py.core.fetcher.Path.exists", return_value=True),
            patch("desktop_py.core.fetcher.wait_for_url_contains", return_value=False),
            patch("desktop_py.core.fetcher_session.log_session_offline") as mock_log_session_offline,
        ):
            mock_playwright.return_value.__enter__.return_value = object()

            valid = validate_account_state(account)

        self.assertTrue(valid)
        mock_log_session_offline.assert_not_called()

    def test_validate_account_state_logs_structured_failure_reason(self):
        account = AccountConfig(name="主账号", state_path="storage/shared.json")

        class FakePageForValidation:
            url = "https://mp.weixin.qq.com/"

            def goto(self, _url, wait_until=None, timeout=None):
                return None

            def content(self):
                return "<html></html>"

            def locator(self, selector, **kwargs):
                return FakeLocator()

            def get_by_text(self, text, exact=False):
                return FakeLocator()

            def close(self):
                return None

        class FakeContextForValidation:
            def __init__(self):
                self.page = FakePageForValidation()

            def new_page(self):
                return self.page

            def close(self):
                return None

        with (
            patch("desktop_py.core.fetcher.sync_playwright") as mock_playwright,
            patch("desktop_py.core.fetcher.create_browser_context", return_value=(None, FakeContextForValidation())),
            patch("desktop_py.core.fetcher.Path.exists", return_value=True),
            patch("desktop_py.core.fetcher.wait_for_url_contains", return_value=False),
            patch("desktop_py.core.fetcher_session.log_session_offline") as mock_log_session_offline,
        ):
            mock_playwright.return_value.__enter__.return_value = object()

            valid = validate_account_state(account)

        self.assertFalse(valid)
        mock_log_session_offline.assert_called_once_with(
            "主账号",
            "未检测到后台账号信息",
            branch="missing_backend_account_signals",
            page_url="https://mp.weixin.qq.com/",
        )

    def test_renew_account_state_recovers_from_root_page_before_marking_failure(self):
        account = AccountConfig(name="主账号", state_path="storage/shared.json")
        write_state = self.write_fake_storage_state

        class FakePageForRenew:
            def __init__(self):
                self.url = "https://mp.weixin.qq.com/"
                self.recovered = False

            def goto(self, _url, wait_until=None, timeout=None):
                return None

            def wait_for_timeout(self, timeout):
                return None

            def content(self):
                if self.recovered:
                    return '<div class="menu_box_account_info">账号设置</div><script>"nickName":"主账号"</script>'
                return "<html></html>"

            def locator(self, selector, **kwargs):
                if selector == "text=小程序":
                    return FakeLocator(count=1, click_cb=self._recover)
                if self.recovered and selector == "div.menu_box_account_info_item[title='切换账号']":
                    return FakeLocator(count=1)
                return FakeLocator()

            def get_by_text(self, text, exact=False):
                return FakeLocator()

            def close(self):
                return None

            def _recover(self):
                self.recovered = True
                self.url = "https://mp.weixin.qq.com/wxamp/index/index?token=1"

        class FakeContextForRenew:
            def __init__(self):
                self.page = FakePageForRenew()

            def new_page(self):
                return self.page

            def storage_state(self, path=None, indexed_db=False):
                write_state(path)

            def close(self):
                return None

        with TemporaryDirectory() as temp_dir:
            state_path = str(Path(temp_dir) / "shared.json")
            Path(state_path).write_text("original", encoding="utf-8")
            account.state_path = state_path
            with (
                patch("desktop_py.core.fetcher.sync_playwright") as mock_playwright,
                patch("desktop_py.core.fetcher.create_browser_context", return_value=(None, FakeContextForRenew())),
                patch("desktop_py.core.fetcher.Path.exists", return_value=True),
                patch("desktop_py.core.fetcher.wait_for_url_contains", return_value=False),
                patch("desktop_py.core.fetcher_session.log_session_renew_failed") as mock_log_session_renew_failed,
            ):
                mock_playwright.return_value.__enter__.return_value = object()

                valid = renew_account_state(account)

        self.assertTrue(valid)
        mock_log_session_renew_failed.assert_not_called()

    def test_validate_account_state_runs_in_helper_thread_when_asyncio_loop_exists(self):
        account = AccountConfig(name="主账号", state_path="storage/shared.json")

        async def runner():
            with patch("desktop_py.core.fetcher.validate_account_state_impl", return_value=True) as mock_impl:
                valid = validate_account_state(account)
            return valid, mock_impl.call_count

        valid, call_count = asyncio.run(runner())

        self.assertTrue(valid)
        self.assertEqual(call_count, 1)

    def test_save_login_state_runs_in_helper_thread_when_asyncio_loop_exists(self):
        account = AccountConfig(name="主账号", state_path="storage/shared.json")

        async def runner():
            with patch(
                "desktop_py.core.fetcher.save_login_state_impl", return_value="storage/shared.json"
            ) as mock_impl:
                state_path = save_login_state(account, 120)
            return state_path, mock_impl.call_count

        state_path, call_count = asyncio.run(runner())

        self.assertEqual(state_path, "storage/shared.json")
        self.assertEqual(call_count, 1)

    def test_save_login_state_with_profile_runs_in_helper_thread_when_asyncio_loop_exists(self):
        account = AccountConfig(name="主账号", state_path="storage/shared.json")

        async def runner():
            with patch(
                "desktop_py.core.fetcher.save_login_state_with_profile_impl",
                return_value="storage/shared.json",
            ) as mock_impl:
                state_path = save_login_state_with_profile(account, 120, "C:/profile")
            return state_path, mock_impl.call_count, mock_impl.call_args.args

        state_path, call_count, args = asyncio.run(runner())

        self.assertEqual(state_path, "storage/shared.json")
        self.assertEqual(call_count, 1)
        self.assertEqual(args[:3], (account, 120, "C:/profile"))

    def test_fetch_switchable_accounts_runs_in_helper_thread_when_asyncio_loop_exists(self):
        account = AccountConfig(name="主账号", state_path="storage/shared.json")

        async def runner():
            with patch(
                "desktop_py.core.fetcher.fetch_switchable_accounts_impl",
                return_value=["导入账号A", "导入账号B"],
            ) as mock_impl:
                names = fetch_switchable_accounts(account, headless=False, profile_dir="C:/profile")
            return names, mock_impl.call_count, mock_impl.call_args.kwargs

        names, call_count, kwargs = asyncio.run(runner())

        self.assertEqual(names, ["导入账号A", "导入账号B"])
        self.assertEqual(call_count, 1)
        self.assertFalse(kwargs["headless"])
        self.assertEqual(kwargs["profile_dir"], "C:/profile")

    def test_renew_account_state_runs_in_helper_thread_when_asyncio_loop_exists(self):
        account = AccountConfig(name="主账号", state_path="storage/shared.json")

        async def runner():
            with patch("desktop_py.core.fetcher.renew_account_state_impl", return_value=True) as mock_impl:
                valid = renew_account_state(account)
            return valid, mock_impl.call_count

        valid, call_count = asyncio.run(runner())

        self.assertTrue(valid)
        self.assertEqual(call_count, 1)

    def test_renew_account_state_persists_after_page_already_closed(self):
        calls: list[str] = []
        write_state = self.write_fake_storage_state

        class FakePageForRenew:
            def __init__(self):
                self.url = "https://mp.weixin.qq.com/wxamp/index/index?token=1"
                self.closed = False

            def goto(self, _url, wait_until=None, timeout=None):
                calls.append("goto")

            def close(self):
                self.closed = True
                calls.append("page")

            def is_closed(self):
                return self.closed

            def wait_for_timeout(self, timeout):
                calls.append(f"wait:{timeout}")

        class FakeContextForRenew:
            def __init__(self):
                self.page = FakePageForRenew()

            def new_page(self):
                return self.page

            def storage_state(self, path=None, indexed_db=False):
                calls.append(f"storage:{path}:{indexed_db}")
                write_state(path)

            def close(self):
                calls.append("context")

        fake_browser = type("FakeBrowser", (), {"close": lambda self: calls.append("browser")})()

        with TemporaryDirectory() as temp_dir:
            state_path = str(Path(temp_dir) / "shared.json")
            Path(state_path).write_text("original", encoding="utf-8")
            with (
                patch("desktop_py.core.fetcher.sync_playwright") as mock_playwright,
                patch(
                    "desktop_py.core.fetcher.create_browser_context",
                    return_value=(fake_browser, FakeContextForRenew()),
                ),
                patch("desktop_py.core.fetcher.wait_for_url_contains", return_value=True),
            ):
                mock_playwright.return_value.__enter__.return_value = object()

                valid = renew_account_state(AccountConfig(name="accountA", state_path=state_path), profile_dir="")

        self.assertTrue(valid)
        self.assertIn("page", calls)
        self.assertTrue(any(".renew.tmp" in call for call in calls if call.startswith("storage:")))
