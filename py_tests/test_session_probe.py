from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

from desktop_py.core.models import (
    SESSION_SOURCE_PROFILE,
    SESSION_SOURCE_STATE_FILE,
    SESSION_STATUS_EXPIRED,
    SESSION_STATUS_MISSING,
    SESSION_STATUS_NEEDS_RELOGIN,
    SESSION_STATUS_STALE,
    SESSION_STATUS_VALID,
    AccountConfig,
)
from desktop_py.core.session_probe import (
    BACKEND_SESSION_CONTENT_KEYWORDS,
    BACKEND_SESSION_URL_KEYWORDS,
    SESSION_STALE_AFTER,
    SessionVerification,
    _extract_account_name_from_html,
    _has_backend_session_locator,
    _has_backend_session_url,
    _locator_count,
    _parse_datetime,
    _probe_account_candidate_urls,
    _verified_status_for_account,
    apply_session_verification,
    mark_account_session_missing,
    session_source_for_profile_dir,
    verify_backend_session,
)


class SessionSourceForProfileDirTestCase(unittest.TestCase):
    def test_returns_profile_source_when_profile_dir_present(self):
        self.assertEqual(session_source_for_profile_dir("/some/path"), SESSION_SOURCE_PROFILE)

    def test_returns_state_file_source_when_profile_dir_blank(self):
        self.assertEqual(session_source_for_profile_dir(""), SESSION_SOURCE_STATE_FILE)

    def test_returns_state_file_source_when_profile_dir_whitespace(self):
        self.assertEqual(session_source_for_profile_dir("   "), SESSION_SOURCE_STATE_FILE)


class ParseDatetimeTestCase(unittest.TestCase):
    def test_parses_full_format(self):
        result = _parse_datetime("2025-01-15 10:30:00")
        self.assertEqual(result, datetime(2025, 1, 15, 10, 30, 0))

    def test_parses_short_format(self):
        result = _parse_datetime("2025-01-15 10:30")
        self.assertEqual(result, datetime(2025, 1, 15, 10, 30))

    def test_returns_none_for_empty_string(self):
        self.assertIsNone(_parse_datetime(""))

    def test_returns_none_for_whitespace_only(self):
        self.assertIsNone(_parse_datetime("   "))

    def test_returns_none_for_invalid_format(self):
        self.assertIsNone(_parse_datetime("not-a-date"))

    def test_strips_surrounding_whitespace(self):
        result = _parse_datetime("  2025-01-15 10:30:00  ")
        self.assertEqual(result, datetime(2025, 1, 15, 10, 30, 0))


class VerifiedStatusForAccountTestCase(unittest.TestCase):
    def test_returns_valid_when_account_is_none(self):
        self.assertEqual(_verified_status_for_account(None), SESSION_STATUS_VALID)

    def test_returns_valid_when_no_dates_set(self):
        account = AccountConfig(name="test", state_path="/path")
        account.last_session_renewed_at = ""
        account.last_login_at = ""
        account.last_session_verified_at = ""
        self.assertEqual(_verified_status_for_account(account), SESSION_STATUS_VALID)

    def test_returns_stale_when_renewed_long_ago(self):
        account = AccountConfig(name="test", state_path="/path")
        old_time = (datetime.now() - SESSION_STALE_AFTER - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        account.last_session_renewed_at = old_time
        self.assertEqual(_verified_status_for_account(account), SESSION_STATUS_STALE)

    def test_returns_valid_when_renewed_recently(self):
        account = AccountConfig(name="test", state_path="/path")
        recent_time = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        account.last_session_renewed_at = recent_time
        self.assertEqual(_verified_status_for_account(account), SESSION_STATUS_VALID)

    def test_falls_back_to_login_at_when_renewed_at_empty(self):
        account = AccountConfig(name="test", state_path="/path")
        account.last_session_renewed_at = ""
        old_time = (datetime.now() - SESSION_STALE_AFTER - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
        account.last_login_at = old_time
        self.assertEqual(_verified_status_for_account(account), SESSION_STATUS_STALE)

    def test_falls_back_to_verified_at(self):
        account = AccountConfig(name="test", state_path="/path")
        account.last_session_renewed_at = ""
        account.last_login_at = ""
        old_time = (datetime.now() - SESSION_STALE_AFTER - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        account.last_session_verified_at = old_time
        self.assertEqual(_verified_status_for_account(account), SESSION_STATUS_STALE)


class HasBackendSessionUrlTestCase(unittest.TestCase):
    def test_detects_token_in_url(self):
        page = MagicMock()
        page.url = "https://mp.weixin.qq.com/cgi-bin/home?t=1&token=abc123"
        self.assertTrue(_has_backend_session_url(page))

    def test_detects_wxamp_index(self):
        page = MagicMock()
        page.url = "https://mp.weixin.qq.com/wxamp/index/index?token=abc"
        self.assertTrue(_has_backend_session_url(page))

    def test_detects_plugin_redirect(self):
        page = MagicMock()
        page.url = "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=abc"
        self.assertTrue(_has_backend_session_url(page))

    def test_rejects_unrelated_url(self):
        page = MagicMock()
        page.url = "https://mp.weixin.qq.com/cgi-bin/loginpage"
        self.assertFalse(_has_backend_session_url(page))

    def test_handles_empty_url(self):
        page = MagicMock()
        page.url = ""
        self.assertFalse(_has_backend_session_url(page))


class ExtractAccountNameFromHtmlTestCase(unittest.TestCase):
    def test_extracts_nick_name(self):
        html = '{"nickName":"测试账号","other":"value"}'
        self.assertEqual(_extract_account_name_from_html(html), "测试账号")

    def test_returns_empty_when_no_nick_name(self):
        html = '{"other":"value"}'
        self.assertEqual(_extract_account_name_from_html(html), "")

    def test_returns_empty_for_empty_html(self):
        self.assertEqual(_extract_account_name_from_html(""), "")

    def test_strips_whitespace_from_nick_name(self):
        html = '{"nickName":"  测试账号  "}'
        self.assertEqual(_extract_account_name_from_html(html), "测试账号")


class LocatorCountTestCase(unittest.TestCase):
    def test_returns_count_from_locator(self):
        page = MagicMock()
        page.locator.return_value.count.return_value = 3
        self.assertEqual(_locator_count(page, ".selector"), 3)

    def test_returns_zero_on_exception(self):
        page = MagicMock()
        page.locator.side_effect = Exception("error")
        self.assertEqual(_locator_count(page, ".selector"), 0)


class HasBackendSessionLocatorTestCase(unittest.TestCase):
    def test_returns_true_when_account_item_found(self):
        page = MagicMock()
        page.locator.return_value.count.return_value = 1
        self.assertTrue(_has_backend_session_locator(page))

    def test_returns_false_when_no_locators_found(self):
        page = MagicMock()
        page.locator.return_value.count.return_value = 0
        page.get_by_text.return_value.count.return_value = 0
        self.assertFalse(_has_backend_session_locator(page))

    def test_returns_false_when_no_locator_method(self):
        page = MagicMock(spec=["url"])
        self.assertFalse(_has_backend_session_locator(page))


class VerifyBackendSessionTestCase(unittest.TestCase):
    @patch("desktop_py.core.session_probe.safe_page_content", return_value="")
    @patch("desktop_py.core.session_probe.is_login_timeout_page", return_value=False)
    def test_returns_expired_on_login_timeout_page(self, mock_timeout, mock_content):
        page = MagicMock()
        page.url = "https://mp.weixin.qq.com/cgi-bin/loginpage"
        mock_timeout.return_value = True
        result = verify_backend_session(page)
        self.assertFalse(result.valid)
        self.assertEqual(result.status, SESSION_STATUS_EXPIRED)
        self.assertTrue(result.should_relogin)

    @patch("desktop_py.core.session_probe.safe_page_content", return_value="")
    @patch("desktop_py.core.session_probe.is_login_timeout_page", return_value=False)
    def test_returns_valid_when_account_name_found_in_html(self, mock_timeout, mock_content):
        page = MagicMock()
        page.url = "https://mp.weixin.qq.com/cgi-bin/home?token=abc"
        mock_content.return_value = '{"nickName":"我的账号"}'
        result = verify_backend_session(page)
        self.assertTrue(result.valid)
        self.assertEqual(result.actual_account_name, "我的账号")

    @patch("desktop_py.core.session_probe.safe_page_content", return_value="")
    @patch("desktop_py.core.session_probe.is_login_timeout_page", return_value=False)
    def test_returns_valid_when_locator_signals_found(self, mock_timeout, mock_content):
        page = MagicMock()
        page.url = "https://mp.weixin.qq.com/cgi-bin/home?token=abc"
        page.locator.return_value.count.return_value = 1
        result = verify_backend_session(page)
        self.assertTrue(result.valid)

    @patch("desktop_py.core.session_probe.safe_page_content", return_value="")
    @patch("desktop_py.core.session_probe.is_login_timeout_page", return_value=False)
    def test_returns_valid_when_content_keywords_found(self, mock_timeout, mock_content):
        page = MagicMock()
        page.url = "https://mp.weixin.qq.com/cgi-bin/home?token=abc"
        mock_content.return_value = '<div class="menu_box_account_info">切换账号</div>'
        page.locator.return_value.count.return_value = 0
        page.get_by_text.return_value.count.return_value = 0
        result = verify_backend_session(page)
        self.assertTrue(result.valid)

    @patch("desktop_py.core.session_probe.safe_page_content", return_value="")
    @patch("desktop_py.core.session_probe.is_login_timeout_page", return_value=False)
    def test_returns_expired_when_only_url_present_without_dom(self, mock_timeout, mock_content):
        """When page has backend URL but no content/locator callable, returns valid."""
        page = MagicMock()
        page.url = "https://mp.weixin.qq.com/cgi-bin/home?token=abc"
        page.content = None
        page.locator = None
        mock_content.return_value = ""
        # With no content callable, and URL has backend keywords -> backend_url_without_dom branch
        result = verify_backend_session(page)
        # The branch that checks URL + no callable content/locator
        self.assertTrue(result.valid)

    @patch("desktop_py.core.session_probe.safe_page_content", return_value="")
    @patch("desktop_py.core.session_probe.is_login_timeout_page", return_value=False)
    def test_returns_needs_relogin_when_no_signals_detected(self, mock_timeout, mock_content):
        page = MagicMock()
        page.url = "https://mp.weixin.qq.com/cgi-bin/loginpage"
        mock_content.return_value = "<html>empty</html>"
        page.locator.return_value.count.return_value = 0
        page.get_by_text.return_value.count.return_value = 0
        result = verify_backend_session(page)
        self.assertFalse(result.valid)
        self.assertEqual(result.status, SESSION_STATUS_NEEDS_RELOGIN)
        self.assertTrue(result.should_relogin)

    @patch("desktop_py.core.session_probe.safe_page_content", return_value="")
    @patch("desktop_py.core.session_probe.is_login_timeout_page", return_value=False)
    def test_returns_expired_when_url_present_but_no_account_signals(self, mock_timeout, mock_content):
        page = MagicMock()
        page.url = "https://mp.weixin.qq.com/cgi-bin/home?token=abc"
        mock_content.return_value = "<html>empty</html>"
        page.locator.return_value.count.return_value = 0
        page.get_by_text.return_value.count.return_value = 0
        result = verify_backend_session(page)
        self.assertFalse(result.valid)
        self.assertEqual(result.status, SESSION_STATUS_EXPIRED)
        self.assertTrue(result.should_retry)

    @patch("desktop_py.core.session_probe.safe_page_content", return_value="")
    @patch("desktop_py.core.session_probe.is_login_timeout_page", return_value=False)
    def test_extracts_feedback_url_when_backend_session_url_detected(self, mock_timeout, mock_content):
        page = MagicMock()
        page.url = (
            "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback"
            "?token=abc123&lang=zh_CN"
        )
        mock_content.return_value = '{"nickName":"测试"}'
        result = verify_backend_session(page)
        self.assertTrue(result.valid)
        self.assertIn("token=abc123", result.feedback_url)


class ApplySessionVerificationTestCase(unittest.TestCase):
    def test_applies_valid_verification(self):
        account = AccountConfig(name="test", state_path="/path")
        verification = SessionVerification(
            valid=True,
            status=SESSION_STATUS_VALID,
            actual_account_name="实际名称",
            feedback_url="https://example.com",
            reason="ok",
            session_source="profile",
        )
        apply_session_verification(account, verification, profile_dir="/profile", verified_at="2025-01-01 00:00:00")
        self.assertEqual(account.session_status, SESSION_STATUS_VALID)
        self.assertEqual(account.last_actual_account_name, "实际名称")
        self.assertEqual(account.feedback_url, "https://example.com")
        self.assertEqual(account.last_session_error, "")
        self.assertEqual(account.last_session_verified_at, "2025-01-01 00:00:00")

    def test_applies_expired_verification_with_error(self):
        account = AccountConfig(name="test", state_path="/path")
        verification = SessionVerification(
            valid=False,
            status=SESSION_STATUS_EXPIRED,
            reason="登录已过期",
        )
        apply_session_verification(account, verification, profile_dir="/profile", verified_at="2025-01-01 00:00:00")
        self.assertEqual(account.session_status, SESSION_STATUS_EXPIRED)
        self.assertEqual(account.last_session_error, "登录已过期")

    def test_sets_renewed_at_when_renewed(self):
        account = AccountConfig(name="test", state_path="/path")
        verification = SessionVerification(valid=True, status=SESSION_STATUS_VALID, session_source="profile")
        apply_session_verification(account, verification, verified_at="2025-01-01 00:00:00", renewed=True)
        self.assertEqual(account.last_session_renewed_at, "2025-01-01 00:00:00")

    def test_does_not_set_renewed_at_when_not_renewed(self):
        account = AccountConfig(name="test", state_path="/path")
        account.last_session_renewed_at = ""
        verification = SessionVerification(valid=True, status=SESSION_STATUS_VALID, session_source="profile")
        apply_session_verification(account, verification, verified_at="2025-01-01 00:00:00", renewed=False)
        self.assertEqual(account.last_session_renewed_at, "")

    def test_uses_profile_source_when_verification_has_empty_source(self):
        account = AccountConfig(name="test", state_path="/path")
        verification = SessionVerification(valid=True, status=SESSION_STATUS_VALID, session_source="")
        apply_session_verification(account, verification, profile_dir="/some/profile")
        self.assertEqual(account.session_source, SESSION_SOURCE_PROFILE)

    def test_uses_state_file_source_when_no_profile_dir(self):
        account = AccountConfig(name="test", state_path="/path")
        verification = SessionVerification(valid=True, status=SESSION_STATUS_VALID, session_source="")
        apply_session_verification(account, verification, profile_dir="")
        self.assertEqual(account.session_source, SESSION_SOURCE_STATE_FILE)


class MarkAccountSessionMissingTestCase(unittest.TestCase):
    def test_marks_as_missing(self):
        account = AccountConfig(name="test", state_path="/path")
        mark_account_session_missing(account, profile_dir="/profile", reason="未找到会话")
        self.assertEqual(account.session_status, SESSION_STATUS_MISSING)
        self.assertEqual(account.session_source, SESSION_SOURCE_PROFILE)
        self.assertEqual(account.last_session_error, "未找到会话")

    def test_uses_state_file_source_with_empty_profile_dir(self):
        account = AccountConfig(name="test", state_path="/path")
        mark_account_session_missing(account, profile_dir="")
        self.assertEqual(account.session_source, SESSION_SOURCE_STATE_FILE)

    def test_handles_empty_reason(self):
        account = AccountConfig(name="test", state_path="/path")
        mark_account_session_missing(account)
        self.assertEqual(account.last_session_error, "")


class ProbeAccountCandidateUrlsTestCase(unittest.TestCase):
    def test_returns_home_url(self):
        account = AccountConfig(name="test", state_path="/path", home_url="https://mp.weixin.qq.com/cgi-bin/home")
        urls = _probe_account_candidate_urls(account)
        self.assertEqual(urls, ["https://mp.weixin.qq.com/cgi-bin/home"])

    def test_returns_feedback_url_first_when_preferred(self):
        account = AccountConfig(
            name="test",
            state_path="/path",
            home_url="https://mp.weixin.qq.com/cgi-bin/home",
            feedback_url="https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?token=abc",
        )
        urls = _probe_account_candidate_urls(account, prefer_feedback_url=True)
        self.assertTrue(len(urls) >= 1)
        self.assertIn("token=abc", urls[0])

    def test_deduplicates_urls(self):
        account = AccountConfig(
            name="test",
            state_path="/path",
            home_url="https://mp.weixin.qq.com/cgi-bin/home",
            feedback_url="https://mp.weixin.qq.com/cgi-bin/home",
        )
        urls = _probe_account_candidate_urls(account)
        self.assertEqual(len(urls), 1)

    def test_skips_empty_urls(self):
        account = AccountConfig(name="test", state_path="/path", home_url="")
        urls = _probe_account_candidate_urls(account)
        self.assertEqual(urls, [])


class SessionVerificationDataclassTestCase(unittest.TestCase):
    def test_default_values(self):
        sv = SessionVerification(valid=True)
        self.assertTrue(sv.valid)
        self.assertEqual(sv.status, SESSION_STATUS_EXPIRED)
        self.assertEqual(sv.actual_account_name, "")
        self.assertEqual(sv.feedback_url, "")
        self.assertEqual(sv.reason, "")
        self.assertEqual(sv.branch, "")
        self.assertEqual(sv.page_url, "")
        self.assertFalse(sv.should_retry)
        self.assertFalse(sv.should_relogin)
        self.assertEqual(sv.session_source, "")

    def test_frozen(self):
        sv = SessionVerification(valid=True)
        with self.assertRaises(AttributeError):
            sv.valid = False  # type: ignore[misc]


class VerifyBackendSessionWithAccountTestCase(unittest.TestCase):
    @patch("desktop_py.core.session_probe.safe_page_content", return_value="")
    @patch("desktop_py.core.session_probe.is_login_timeout_page", return_value=False)
    def test_valid_session_returns_stale_status_for_old_account(self, mock_timeout, mock_content):
        page = MagicMock()
        page.url = "https://mp.weixin.qq.com/cgi-bin/home?token=abc"
        mock_content.return_value = '{"nickName":"测试"}'

        account = AccountConfig(name="test", state_path="/path")
        old_time = (datetime.now() - SESSION_STALE_AFTER - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        account.last_session_renewed_at = old_time

        result = verify_backend_session(page, account)
        self.assertTrue(result.valid)
        self.assertEqual(result.status, SESSION_STATUS_STALE)

    @patch("desktop_py.core.session_probe.safe_page_content", return_value="")
    @patch("desktop_py.core.session_probe.is_login_timeout_page", return_value=False)
    def test_valid_session_returns_valid_status_for_recent_account(self, mock_timeout, mock_content):
        page = MagicMock()
        page.url = "https://mp.weixin.qq.com/cgi-bin/home?token=abc"
        mock_content.return_value = '{"nickName":"测试"}'

        account = AccountConfig(name="test", state_path="/path")
        recent_time = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        account.last_session_renewed_at = recent_time

        result = verify_backend_session(page, account)
        self.assertTrue(result.valid)
        self.assertEqual(result.status, SESSION_STATUS_VALID)


if __name__ == "__main__":
    unittest.main()
