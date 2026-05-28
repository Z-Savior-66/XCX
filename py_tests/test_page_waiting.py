from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from desktop_py.core.fetcher_common import CancelledError
from desktop_py.core.page_waiting import (
    _is_navigation_content_error,
    is_wechat_mp_root_page_url,
    wait_for_current_account_name,
    wait_for_url_contains,
    wait_or_cancel,
)


class IsWechatMpRootPageUrlTestCase(unittest.TestCase):
    def test_recognizes_root_page(self):
        self.assertTrue(is_wechat_mp_root_page_url("https://mp.weixin.qq.com/"))
        self.assertTrue(is_wechat_mp_root_page_url("https://mp.weixin.qq.com"))

    def test_rejects_path_page(self):
        self.assertFalse(is_wechat_mp_root_page_url("https://mp.weixin.qq.com/wxamp/index"))

    def test_rejects_token_page(self):
        self.assertFalse(is_wechat_mp_root_page_url("https://mp.weixin.qq.com/?token=abc"))

    def test_rejects_external_host(self):
        self.assertFalse(is_wechat_mp_root_page_url("https://example.com/"))

    def test_handles_empty_url(self):
        self.assertFalse(is_wechat_mp_root_page_url(""))


class IsNavigationContentErrorTestCase(unittest.TestCase):
    def test_recognizes_navigating_error(self):
        err = Exception("page.content: Navigating to different page")
        self.assertTrue(_is_navigation_content_error(err))

    def test_recognizes_changing_content_error(self):
        err = Exception("page.content: changing the content")
        self.assertTrue(_is_navigation_content_error(err))

    def test_rejects_other_error(self):
        err = Exception("some other error")
        self.assertFalse(_is_navigation_content_error(err))

    def test_case_insensitive(self):
        err = Exception("PAGE.CONTENT: NAVIGATING")
        self.assertTrue(_is_navigation_content_error(err))


class WaitOrCancelTestCase(unittest.TestCase):
    def test_calls_wait_for_timeout(self):
        page = Mock()
        page.wait_for_timeout = Mock()
        wait_or_cancel(page, 500)
        page.wait_for_timeout.assert_called_once_with(500)

    def test_raises_cancelled_before_wait(self):
        page = Mock()
        with self.assertRaises(CancelledError):
            wait_or_cancel(page, 500, is_cancelled=lambda: True)

    def test_raises_cancelled_after_wait(self):
        page = Mock()
        call_count = 0

        def check_cancelled():
            nonlocal call_count
            call_count += 1
            return call_count > 1

        with self.assertRaises(CancelledError):
            wait_or_cancel(page, 500, is_cancelled=check_cancelled)
        page.wait_for_timeout.assert_called_once()


class WaitForUrlContainsTestCase(unittest.TestCase):
    def test_returns_true_when_keyword_present_immediately(self):
        page = Mock()
        page.url = "https://mp.weixin.qq.com/?token=abc"

        with patch("desktop_py.core.page_waiting.wait_or_cancel"):
            result = wait_for_url_contains(page, ("token=",), timeout_ms=100)
        self.assertTrue(result)

    def test_returns_false_after_timeout(self):
        page = Mock()
        page.url = "https://mp.weixin.qq.com/"

        with patch("desktop_py.core.page_waiting.wait_or_cancel"):
            result = wait_for_url_contains(page, ("token=",), timeout_ms=100)
        self.assertFalse(result)

    def test_matches_any_keyword(self):
        page = Mock()
        page.url = "https://mp.weixin.qq.com/wxamp/index"

        with patch("desktop_py.core.page_waiting.wait_or_cancel"):
            result = wait_for_url_contains(page, ("/wxamp/", "token="), timeout_ms=100)
        self.assertTrue(result)


class WaitForCurrentAccountNameTestCase(unittest.TestCase):
    def test_returns_when_match_found_immediately(self):
        page = Mock()

        def extract_name(pg):
            return "目标账号"

        with patch("desktop_py.core.page_waiting.wait_or_cancel"):
            result = wait_for_current_account_name(
                page, "目标账号", timeout_ms=100, extract_current_account_name_fn=extract_name
            )
        self.assertEqual(result, "目标账号")

    def test_returns_last_result_on_timeout(self):
        page = Mock()

        def extract_name(pg):
            return "其他账号"

        with patch("desktop_py.core.page_waiting.wait_or_cancel"):
            result = wait_for_current_account_name(
                page, "目标账号", timeout_ms=100, extract_current_account_name_fn=extract_name
            )
        self.assertEqual(result, "其他账号")

    def test_handles_empty_extracted_name(self):
        page = Mock()

        def extract_name(pg):
            return ""

        with patch("desktop_py.core.page_waiting.wait_or_cancel"):
            result = wait_for_current_account_name(
                page, "目标账号", timeout_ms=100, extract_current_account_name_fn=extract_name
            )
        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
