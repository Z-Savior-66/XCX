from __future__ import annotations

import unittest

from desktop_py.core.models import AccountConfig
from desktop_py.core.session_links import (
    _group_accounts,
    _preferred_group_feedback_url,
    build_feedback_url_from_token,
    build_ios_refund_feedback_url_from_token,
    canonical_feedback_url,
    canonical_ios_refund_feedback_url,
    extract_token_from_url,
    normalize_group_feedback_urls,
    propagate_account_feedback_url,
    refresh_account_feedback_url,
    sync_account_feedback_url,
)


class ExtractTokenTestCase(unittest.TestCase):
    def test_extracts_token_from_query(self):
        token = extract_token_from_url(
            "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback"
            "?action=plugin_redirect&plugin_uin=1010&token=abc123&lang=zh_CN"
        )
        self.assertEqual(token, "abc123")

    def test_returns_empty_for_empty_url(self):
        self.assertEqual(extract_token_from_url(""), "")

    def test_returns_empty_when_no_token_param(self):
        self.assertEqual(extract_token_from_url("https://mp.weixin.qq.com/path"), "")

    def test_returns_empty_when_token_is_blank(self):
        token = extract_token_from_url("https://mp.weixin.qq.com/path?token=")
        self.assertEqual(token, "")


class BuildFeedbackUrlTestCase(unittest.TestCase):
    def test_builds_url_with_standard_params(self):
        url = build_feedback_url_from_token("abc123")
        self.assertIn("mp.weixin.qq.com", url)
        self.assertIn("token=abc123", url)
        self.assertIn("plugin_uin=1010", url)
        self.assertIn("selected=2", url)

    def test_returns_empty_for_empty_token(self):
        self.assertEqual(build_feedback_url_from_token(""), "")
        self.assertEqual(build_feedback_url_from_token("  "), "")


class BuildIosRefundFeedbackUrlTestCase(unittest.TestCase):
    def test_builds_url_with_ios_params(self):
        url = build_ios_refund_feedback_url_from_token("abc123")
        self.assertIn("mp.weixin.qq.com", url)
        self.assertIn("token=abc123", url)
        self.assertIn("plugin_uin=1039", url)
        self.assertIn("old-teenager-refund-process", url)

    def test_returns_empty_for_empty_token(self):
        self.assertEqual(build_ios_refund_feedback_url_from_token(""), "")


class CanonicalFeedbackUrlTestCase(unittest.TestCase):
    def test_normalizes_valid_backend_url(self):
        url = canonical_feedback_url(
            "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback"
            "?action=plugin_redirect&plugin_uin=1010&token=abc123"
        )
        self.assertIn("token=abc123", url)
        self.assertIn("gameFeedback", url)

    def test_returns_empty_for_url_without_token(self):
        self.assertEqual(
            canonical_feedback_url("https://mp.weixin.qq.com/path"),
            "",
        )

    def test_returns_empty_for_external_host(self):
        self.assertEqual(
            canonical_feedback_url("https://example.com/wxamp/page?token=abc123"),
            "",
        )

    def test_returns_empty_for_empty_url(self):
        self.assertEqual(canonical_feedback_url(""), "")

    def test_rebuilds_url_with_only_token_preserved(self):
        """旧 URL 中除 token 外的参数不保留，全部使用标准参数重建。"""
        url = canonical_feedback_url("https://mp.weixin.qq.com/wxamp/index/index?token=xyz&other=stale")
        self.assertIn("token=xyz", url)
        self.assertIn("plugin_uin=1010", url)
        self.assertNotIn("other=stale", url)


class CanonicalIosRefundFeedbackUrlTestCase(unittest.TestCase):
    def test_normalizes_valid_url(self):
        url = canonical_ios_refund_feedback_url(
            "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?action=plugin_redirect&token=abc123"
        )
        self.assertIn("token=abc123", url)
        self.assertIn("plugin_uin=1039", url)

    def test_returns_empty_for_url_without_token(self):
        self.assertEqual(
            canonical_ios_refund_feedback_url("https://mp.weixin.qq.com/path"),
            "",
        )

    def test_returns_empty_for_external_host(self):
        self.assertEqual(
            canonical_ios_refund_feedback_url("https://example.com/wxamp/page?token=abc"),
            "",
        )

    def test_returns_empty_for_empty_url(self):
        self.assertEqual(canonical_ios_refund_feedback_url(""), "")


class RefreshAccountFeedbackUrlTestCase(unittest.TestCase):
    def test_updates_account_when_different(self):
        account = AccountConfig(name="test", state_path="", feedback_url="old_url?token=old")
        result = refresh_account_feedback_url(
            account,
            "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?action=plugin_redirect&token=new_token",
        )
        self.assertTrue(result)
        self.assertIn("token=new_token", account.feedback_url)

    def test_no_update_when_same(self):
        page_url = "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback?action=plugin_redirect&token=same"
        canonical = canonical_feedback_url(page_url)
        account = AccountConfig(name="test", state_path="", feedback_url=canonical)
        result = refresh_account_feedback_url(account, page_url)
        self.assertFalse(result)

    def test_no_update_when_token_missing(self):
        account = AccountConfig(name="test", state_path="", feedback_url="old")
        result = refresh_account_feedback_url(account, "https://mp.weixin.qq.com/path")
        self.assertFalse(result)
        self.assertEqual(account.feedback_url, "old")


class GroupAccountsTestCase(unittest.TestCase):
    def test_filters_by_state_path(self):
        accounts = [
            AccountConfig(name="a", state_path="/data/a.json"),
            AccountConfig(name="b", state_path="/data/b.json"),
            AccountConfig(name="c", state_path="/data/a.json"),
        ]
        result = _group_accounts(accounts, "/data/a.json")
        self.assertEqual([a.name for a in result], ["a", "c"])

    def test_returns_empty_for_empty_state_path(self):
        accounts = [AccountConfig(name="a", state_path="/data/a.json")]
        self.assertEqual(_group_accounts(accounts, ""), [])
        self.assertEqual(_group_accounts(accounts, "  "), [])


class PreferredGroupFeedbackUrlTestCase(unittest.TestCase):
    def test_prefers_preferred_account(self):
        accounts = [
            AccountConfig(name="other", state_path="/data/a.json", feedback_url=""),
            AccountConfig(
                name="pref",
                state_path="/data/a.json",
                feedback_url="https://mp.weixin.qq.com/wxamp/frame/gameFeedback?token=tok1",
            ),
        ]
        preferred = AccountConfig(
            name="pref",
            state_path="/data/a.json",
            feedback_url="https://mp.weixin.qq.com/wxamp/frame/gameFeedback?token=tok1",
        )
        url = _preferred_group_feedback_url(accounts, "/data/a.json", preferred_account=preferred)
        self.assertIn("token=tok1", url)

    def test_falls_back_to_entry_account(self):
        accounts = [
            AccountConfig(
                name="entry",
                state_path="/data/a.json",
                is_entry_account=True,
                feedback_url="https://mp.weixin.qq.com/wxamp/frame/gameFeedback?token=entry_tok",
            ),
            AccountConfig(name="other", state_path="/data/a.json", feedback_url=""),
        ]
        url = _preferred_group_feedback_url(accounts, "/data/a.json")
        self.assertIn("token=entry_tok", url)

    def test_returns_empty_when_no_valid_token(self):
        accounts = [
            AccountConfig(name="a", state_path="/data/a.json", feedback_url=""),
            AccountConfig(name="b", state_path="/data/a.json", feedback_url="invalid"),
        ]
        self.assertEqual(_preferred_group_feedback_url(accounts, "/data/a.json"), "")


class SyncAccountFeedbackUrlTestCase(unittest.TestCase):
    def test_syncs_from_own_canonical_url(self):
        canonical = canonical_feedback_url(
            "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback"
            "?action=plugin_redirect&plugin_uin=1010&token=tok&selected=2&lang=zh_CN"
        )
        account = AccountConfig(
            name="test",
            state_path="/data/a.json",
            feedback_url=canonical,
        )
        result = sync_account_feedback_url([account], account)
        self.assertFalse(result)

    def test_syncs_from_group_when_own_token_missing(self):
        accounts = [
            AccountConfig(
                name="source",
                state_path="/data/a.json",
                feedback_url="https://mp.weixin.qq.com/wxamp/frame/gameFeedback?token=shared",
            ),
            AccountConfig(name="target", state_path="/data/a.json", feedback_url=""),
        ]
        result = sync_account_feedback_url(accounts, accounts[1])
        self.assertTrue(result)
        self.assertIn("token=shared", accounts[1].feedback_url)

    def test_no_sync_when_state_path_empty(self):
        account = AccountConfig(name="test", state_path="", feedback_url="")
        self.assertFalse(sync_account_feedback_url([account], account))


class PropagateAccountFeedbackUrlTestCase(unittest.TestCase):
    def test_propagates_to_group_members(self):
        accounts = [
            AccountConfig(
                name="source",
                state_path="/data/a.json",
                feedback_url="https://mp.weixin.qq.com/wxamp/frame/gameFeedback?token=shared",
            ),
            AccountConfig(name="target", state_path="/data/a.json", feedback_url=""),
        ]
        result = propagate_account_feedback_url(accounts, accounts[0])
        self.assertTrue(result)
        self.assertIn("token=shared", accounts[1].feedback_url)

    def test_skips_when_no_token(self):
        account = AccountConfig(name="test", state_path="/data/a.json", feedback_url="")
        self.assertFalse(propagate_account_feedback_url([account], account))

    def test_skips_already_synced(self):
        canonical = canonical_feedback_url(
            "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback"
            "?action=plugin_redirect&plugin_uin=1010&token=shared&selected=2&lang=zh_CN"
        )
        accounts = [
            AccountConfig(name="a", state_path="/data/a.json", feedback_url=canonical),
            AccountConfig(name="b", state_path="/data/a.json", feedback_url=canonical),
        ]
        self.assertFalse(propagate_account_feedback_url(accounts, accounts[0]))


class NormalizeGroupFeedbackUrlsTestCase(unittest.TestCase):
    def test_returns_false_when_all_synced(self):
        canonical = canonical_feedback_url(
            "https://mp.weixin.qq.com/wxamp/frame/pluginRedirect/gameFeedback"
            "?action=plugin_redirect&plugin_uin=1010&token=shared&selected=2&lang=zh_CN"
        )
        accounts = [
            AccountConfig(name="a", state_path="/data/a.json", feedback_url=canonical),
            AccountConfig(name="b", state_path="/data/a.json", feedback_url=canonical),
        ]
        self.assertFalse(normalize_group_feedback_urls(accounts))

    def test_returns_true_when_some_need_sync(self):
        accounts = [
            AccountConfig(
                name="source",
                state_path="/data/a.json",
                feedback_url="https://mp.weixin.qq.com/wxamp/frame/gameFeedback?token=shared",
            ),
            AccountConfig(name="target", state_path="/data/a.json", feedback_url=""),
        ]
        self.assertTrue(normalize_group_feedback_urls(accounts))


if __name__ == "__main__":
    unittest.main()
