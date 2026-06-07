"""Tests for desktop_py.core.fetcher_navigation."""

import unittest
from unittest.mock import MagicMock, patch

from desktop_py.core.fetcher_navigation import (
    _find_business_frame,
    page_current_account_name,
    page_has_backend_session,
    page_home_ready,
    recover_timeout_page_if_needed,
    set_page_current_account_name,
    set_page_home_ready,
    wait_for_timeout,
)


class PageCurrentAccountNameTestCase(unittest.TestCase):
    def test_returns_cached_name(self):
        page = MagicMock()
        page._current_account_name_cache = "测试账号"
        self.assertEqual(page_current_account_name(page), "测试账号")

    def test_returns_empty_string_when_no_cache(self):
        page = MagicMock(spec=[])
        self.assertEqual(page_current_account_name(page), "")

    def test_returns_empty_string_for_non_string_cache(self):
        # When the cache exists but is not a string, the function strips/str() it
        page = MagicMock(spec=[])
        # With spec=[], getattr returns "" for missing attr, so str().strip() = ""
        self.assertEqual(page_current_account_name(page), "")


class SetPageCurrentAccountNameTestCase(unittest.TestCase):
    def test_sets_name_on_page(self):
        page = MagicMock()
        set_page_current_account_name(page, "新账号")
        self.assertEqual(page._current_account_name_cache, "新账号")

    def test_strips_whitespace(self):
        page = MagicMock()
        set_page_current_account_name(page, "  带空格  ")
        self.assertEqual(page._current_account_name_cache, "带空格")

    def test_silently_ignores_exception(self):
        # Should not raise even with a problematic object
        set_page_current_account_name(None, "test")


class PageHasBackendSessionTestCase(unittest.TestCase):
    def test_returns_true_when_url_contains_token(self):
        page = MagicMock()
        page.url = "https://mp.weixin.qq.com/cgi-bin/home?token=12345"
        self.assertTrue(page_has_backend_session(page))

    def test_returns_true_when_url_contains_wxamp_index(self):
        page = MagicMock()
        page.url = "https://mp.weixin.qq.com/wxamp/index/index"
        self.assertTrue(page_has_backend_session(page))

    def test_returns_true_when_url_contains_game_feedback_redirect(self):
        page = MagicMock()
        page.url = "https://mp.weixin.qq.com/pluginRedirect/gameFeedback"
        self.assertTrue(page_has_backend_session(page))

    def test_returns_false_for_login_page(self):
        page = MagicMock()
        page.url = "https://mp.weixin.qq.com/cgi-bin/loginpage"
        self.assertFalse(page_has_backend_session(page))

    def test_returns_false_for_empty_url(self):
        page = MagicMock()
        page.url = ""
        self.assertFalse(page_has_backend_session(page))

    def test_returns_false_when_url_is_none(self):
        page = MagicMock(spec=[])
        self.assertFalse(page_has_backend_session(page))

    def test_returns_false_on_exception(self):
        page = MagicMock()
        type(page).url = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))
        self.assertFalse(page_has_backend_session(page))


class WaitForTimeoutTestCase(unittest.TestCase):
    def test_delegates_to_page_wait_for_timeout(self):
        page = MagicMock()
        wait_for_timeout(page, 500)
        page.wait_for_timeout.assert_called_once_with(500)

    def test_accepts_cancel_check(self):
        page = MagicMock()
        cancel = MagicMock(return_value=False)
        wait_for_timeout(page, 1000, cancel)
        page.wait_for_timeout.assert_called_once_with(1000)


class FindBusinessFrameTestCase(unittest.TestCase):
    def test_returns_frame_named_js_iframe(self):
        frame = MagicMock()
        frame.name = "js_iframe"
        frame.url = "https://example.com"
        page = MagicMock()
        page.frames = [frame]
        self.assertIs(_find_business_frame(page), frame)

    def test_returns_frame_with_game_index_url(self):
        frame = MagicMock()
        frame.name = ""
        frame.url = "https://gamemp.weixin.qq.com/minigame/index.html"
        page = MagicMock()
        page.frames = [frame]
        self.assertIs(_find_business_frame(page), frame)

    def test_returns_none_when_no_matching_frame(self):
        frame = MagicMock()
        frame.name = "other"
        frame.url = "https://example.com"
        page = MagicMock()
        page.frames = [frame]
        self.assertIsNone(_find_business_frame(page))

    def test_returns_none_when_no_frames(self):
        page = MagicMock()
        page.frames = []
        self.assertIsNone(_find_business_frame(page))

    def test_returns_none_when_frames_attribute_missing(self):
        page = MagicMock(spec=[])
        self.assertIsNone(_find_business_frame(page))

    def test_skips_frames_that_raise_on_name_access(self):
        good_frame = MagicMock()
        good_frame.name = "js_iframe"
        good_frame.url = "https://example.com"

        bad_frame = MagicMock()
        type(bad_frame).name = property(lambda self: (_ for _ in ()).throw(RuntimeError("fail")))

        page = MagicMock()
        page.frames = [bad_frame, good_frame]
        # bad_frame raises on name access -> caught by except -> continue -> good_frame matches
        result = _find_business_frame(page)
        self.assertIs(result, good_frame)


class PageHomeReadyTestCase(unittest.TestCase):
    def test_default_is_false(self):
        page = MagicMock(spec=[])
        self.assertFalse(page_home_ready(page))

    def test_returns_true_after_set(self):
        page = MagicMock()
        set_page_home_ready(page, True)
        self.assertTrue(page_home_ready(page))

    def test_returns_false_after_set_false(self):
        page = MagicMock()
        set_page_home_ready(page, True)
        set_page_home_ready(page, False)
        self.assertFalse(page_home_ready(page))

    def test_set_page_home_ready_silently_ignores_exception(self):
        set_page_home_ready(None, True)

    def test_page_home_ready_silently_ignores_exception(self):
        self.assertFalse(page_home_ready(None))


class RecoverTimeoutPageIfNeededTestCase(unittest.TestCase):
    @patch("desktop_py.core.fetcher_navigation.recover_login_timeout_page", return_value=True)
    def test_returns_true_when_recovery_succeeds(self, mock_recover):
        page = MagicMock()
        log_fn = MagicMock()
        safe_page_content_fn = MagicMock()
        result = recover_timeout_page_if_needed(
            page,
            logger=None,
            log_fn=log_fn,
            safe_page_content_fn=safe_page_content_fn,
            is_cancelled=None,
        )
        self.assertTrue(result)
        mock_recover.assert_called_once()

    @patch("desktop_py.core.fetcher_navigation.recover_login_timeout_page", return_value=False)
    def test_returns_false_when_no_recovery_needed(self, mock_recover):
        page = MagicMock()
        log_fn = MagicMock()
        safe_page_content_fn = MagicMock()
        result = recover_timeout_page_if_needed(
            page,
            logger=None,
            log_fn=log_fn,
            safe_page_content_fn=safe_page_content_fn,
            is_cancelled=None,
        )
        self.assertFalse(result)

    @patch("desktop_py.core.fetcher_navigation.recover_login_timeout_page", return_value=True)
    def test_passes_cancel_check_through(self, mock_recover):
        page = MagicMock()
        cancel = MagicMock(return_value=False)
        log_fn = MagicMock()
        safe_page_content_fn = MagicMock()
        recover_timeout_page_if_needed(
            page,
            logger=None,
            log_fn=log_fn,
            safe_page_content_fn=safe_page_content_fn,
            is_cancelled=cancel,
        )
        _, kwargs = mock_recover.call_args
        self.assertIs(kwargs["is_cancelled"], cancel)


if __name__ == "__main__":
    unittest.main()
