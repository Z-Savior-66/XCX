from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock

from desktop_py.core import fetcher_common
from desktop_py.core.fetcher_common import (
    FetchError,
    FetchErrorCode,
    _log,
    _page_is_closed,
    account_state_path,
    ensure_account_session_available,
    fetch_error_code,
    normalize_profile_dir,
)
from desktop_py.core.models import AccountConfig


class PageIsClosedTestCase(unittest.TestCase):
    def test_returns_true_for_none(self):
        self.assertTrue(_page_is_closed(None))

    def test_returns_true_when_is_closed_is_true(self):
        page = Mock()
        page.is_closed.return_value = True
        self.assertTrue(_page_is_closed(page))

    def test_returns_false_when_is_closed_is_false(self):
        page = Mock()
        page.is_closed.return_value = False
        self.assertFalse(_page_is_closed(page))

    def test_returns_false_when_is_closed_is_non_callable(self):
        page = Mock()
        page.is_closed = "not_a_function"
        self.assertFalse(_page_is_closed(page))

    def test_returns_true_when_is_closed_raises(self):
        page = Mock()
        page.is_closed.side_effect = RuntimeError("boom")
        self.assertTrue(_page_is_closed(page))


class NormalizeProfileDirTestCase(unittest.TestCase):
    def test_passes_through_to_validator(self):
        validator = Mock(return_value="/validated/path")
        result = normalize_profile_dir("/some/path", validate_shared_browser_profile_dir_fn=validator)
        self.assertEqual(result, "/validated/path")
        validator.assert_called_once_with("/some/path")

    def test_returns_empty_for_blank(self):
        validator = Mock()
        self.assertEqual(
            normalize_profile_dir("", validate_shared_browser_profile_dir_fn=validator),
            "",
        )
        self.assertEqual(
            normalize_profile_dir("  ", validate_shared_browser_profile_dir_fn=validator),
            "",
        )
        validator.assert_not_called()


class AccountStatePathTestCase(unittest.TestCase):
    def test_converts_to_path(self):
        account = AccountConfig(name="test", state_path="/data/state.json")
        self.assertEqual(account_state_path(account), Path("/data/state.json"))


class FetchErrorCodeTestCase(unittest.TestCase):
    def test_extracts_fetch_error_code(self):
        err = FetchError("fail", code=FetchErrorCode.SESSION_STATE_INVALID)
        self.assertEqual(fetch_error_code(err), "session_state_invalid")

    def test_extracts_string_code(self):
        err = FetchError("fail", code="custom_code")
        self.assertEqual(fetch_error_code(err), "custom_code")

    def test_returns_empty_for_no_code(self):
        err = FetchError("fail")
        self.assertEqual(fetch_error_code(err), "")

    def test_returns_empty_for_plain_exception(self):
        self.assertEqual(fetch_error_code(RuntimeError("fail")), "")


class GuardedPageGotoTestCase(unittest.TestCase):
    def test_wraps_name_resolution_failure_with_chinese_fetch_error(self):
        class FailingPage:
            def goto(self, url, wait_until=None, timeout=None):
                raise RuntimeError(
                    "Page.goto: net::ERR_NAME_NOT_RESOLVED at https://mp.weixin.qq.com/\n"
                    "Call log:\n"
                    '  - navigating to "https://mp.weixin.qq.com/", waiting until "domcontentloaded"'
                )

        with self.assertRaises(FetchError) as ctx:
            fetcher_common.guarded_page_goto(
                FailingPage(),
                "https://mp.weixin.qq.com/",
                wait_until="domcontentloaded",
                timeout=60000,
            )

        self.assertEqual(fetch_error_code(ctx.exception), "network_navigation_failed")
        self.assertIn("无法访问微信后台", str(ctx.exception))
        self.assertIn("网络、DNS 或代理", str(ctx.exception))
        self.assertEqual(ctx.exception.evidence[0]["metadata"]["target_url"], "https://mp.weixin.qq.com/")


class EnsureAccountSessionAvailableTestCase(unittest.TestCase):
    def test_returns_path_when_file_exists(self):
        account = AccountConfig(name="test", state_path="/data/state.json")
        result = ensure_account_session_available(account, "", path_exists_fn=lambda p: True, error_cls=ValueError)
        self.assertEqual(result, Path("/data/state.json"))

    def test_returns_path_when_profile_dir_provided(self):
        account = AccountConfig(name="test", state_path="/data/state.json")
        result = ensure_account_session_available(
            account, "/profile/dir", path_exists_fn=lambda p: False, error_cls=ValueError
        )
        self.assertIsNotNone(result)

    def test_raises_fetch_error_when_missing_and_no_profile(self):
        account = AccountConfig(name="test", state_path="/data/missing.json")
        with self.assertRaises(FetchError) as ctx:
            ensure_account_session_available(account, "", path_exists_fn=lambda p: False, error_cls=FetchError)
        self.assertEqual(ctx.exception.code, FetchErrorCode.SESSION_STATE_INVALID)
        self.assertIn("缺少登录态文件", str(ctx.exception))

    def test_raises_custom_error_class(self):
        account = AccountConfig(name="test", state_path="/data/missing.json")

        class CustomError(Exception):
            pass

        with self.assertRaises(CustomError):
            ensure_account_session_available(account, "", path_exists_fn=lambda p: False, error_cls=CustomError)

    def test_returns_none_when_no_error_class(self):
        account = AccountConfig(name="test", state_path="/data/missing.json")
        result = ensure_account_session_available(account, "", path_exists_fn=lambda p: False)
        self.assertIsNone(result)


class LogTestCase(unittest.TestCase):
    def test_calls_logger_when_provided(self):
        logger = Mock()
        _log(logger, "test message")
        logger.assert_called_once_with("test message")

    def test_noop_when_logger_is_none(self):
        _log(None, "test message")


if __name__ == "__main__":
    unittest.main()
