import asyncio
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from desktop_py.core.fetcher import (
    extract_current_account_name,
    fetch_account,
    fetch_accounts_batch,
    fetch_switchable_accounts,
    renew_account_state,
    save_login_state,
    save_login_state_with_profile,
    validate_account_state,
    wait_for_current_account_name,
    wait_for_switch_account_items,
)
from desktop_py.core.fetcher_page_strategy import register_response_capture
from desktop_py.core.fetcher_pipeline import fetch_account_in_page_impl
from desktop_py.core.fetcher_pipeline import resolve_bootstrap_url_impl as resolve_bootstrap_url
from desktop_py.core.fetcher_runtime import close_all_group_runtimes
from desktop_py.core.fetcher_support import (
    CancelledError,
    _capture_response_payload,
    _close_context_and_browser,
    _fallback_from_responses,
    analyze_storage_state,
    build_feedback_url,
    business_iframe_selector,
    classify_refund_response_type,
    extract_response_token,
    is_login_timeout_page,
    is_wechat_mp_root_page_url,
    persist_storage_state,
    recover_login_timeout_page,
    recover_wechat_mp_root_page,
    safe_page_content,
    wait_for_iframe_ready,
    wait_for_url_contains,
    wait_or_cancel,
)
from desktop_py.core.fetcher_switching import (
    find_switch_entry_impl as find_switch_entry,
)
from desktop_py.core.fetcher_switching import (
    prepare_switch_account_page_impl as prepare_switch_account_page,
)
from desktop_py.core.fetcher_switching import (
    should_retry_switch_from_home_impl as should_retry_switch_from_home,
)
from desktop_py.core.fetcher_switching import (
    should_switch_account_impl as should_switch_account,
)
from desktop_py.core.fetcher_switching import (
    should_switch_for_account_impl as should_switch_for_account,
)
from desktop_py.core.fetcher_switching import (
    wait_for_account_switch_stable_impl as wait_for_account_switch_stable,
)
from desktop_py.core.models import AccountConfig, FetchResult
from desktop_py.core.notification_page_strategy import (
    build_notification_summary,
    filter_target_unread_notifications,
)
from desktop_py.core.parser import extract_labeled_datetime

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "fetcher"


class FakeElementHandle:
    def __init__(self, frame):
        self._frame = frame

    def content_frame(self):
        return self._frame


class FakeFrame:
    def __init__(self, text: str = "", html: str = "", url: str = "https://example.com/frame"):
        self.url = url
        self._text = text
        self._html = html
        self.load_state_calls: list[tuple[str | None, int | None]] = []

    def wait_for_load_state(self, state=None, timeout=None):
        self.load_state_calls.append((state, timeout))

    def locator(self, selector):
        if selector == "body":
            return FakeLocator(count=1, text=self._text, html=self._html)
        return FakeLocator()


class FakeLocator:
    def __init__(
        self,
        count: int = 0,
        counts: list[int] | None = None,
        frame=None,
        text: str = "",
        html: str = "",
        click_cb=None,
    ):
        self._count = count
        self._counts = list(counts) if counts is not None else None
        self._frame = frame
        self._text = text
        self._html = html
        self._click_cb = click_cb
        self.first = self

    def count(self) -> int:
        if self._counts is not None:
            if len(self._counts) > 1:
                return self._counts.pop(0)
            return self._counts[0]
        return self._count

    def evaluate(self, _script):
        if self._click_cb is not None:
            self._click_cb()
        return None

    def click(self, timeout=None):
        if self._click_cb is not None:
            self._click_cb()
        return None

    def element_handle(self):
        if self._frame is None:
            return None
        return FakeElementHandle(self._frame)

    def text_content(self, timeout=None):
        return self._text

    def inner_html(self, timeout=None):
        return self._html


class FakePage:
    def __init__(self, locator_map=None, text_map=None):
        self.locator_map = locator_map or {}
        self.text_map = text_map or {}
        self.wait_calls: list[int] = []
        self.load_state_calls: list[tuple[str | None, int | None]] = []
        self.url = ""
        self._current_account_names: list[str] = []
        self._content_results: list[object] = []

    def locator(self, selector, **kwargs):
        key = (selector, kwargs.get("has_text"))
        return self.locator_map.get(key, FakeLocator())

    def get_by_text(self, text, exact=False):
        key = (text, exact)
        return self.text_map.get(key, FakeLocator())

    def wait_for_timeout(self, timeout):
        self.wait_calls.append(timeout)

    def wait_for_load_state(self, state=None, timeout=None):
        self.load_state_calls.append((state, timeout))
        return None

    def set_current_account_names(self, names: list[str]):
        self._current_account_names = list(names)

    def set_content_results(self, results: list[object]):
        self._content_results = list(results)

    def content(self):
        if self._content_results:
            result = self._content_results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        return ""


class FakeResponse:
    def __init__(
        self, text: str, content_type: str = "application/json", url: str = "https://example.com/api", status: int = 200
    ):
        self._text = text
        self.headers = {"content-type": content_type}
        self.url = url
        self.status = status

    def text(self):
        return self._text


class FixturePage:
    def __init__(self, html: str):
        self.html = html

    def locator(self, selector, **kwargs):
        has_text = kwargs.get("has_text")
        if selector == "div.menu_box_account_info_item[title='切换账号']":
            return FakeLocator(count=1 if 'title="切换账号"' in self.html else 0)
        if selector == ".menu_box_account_info_item":
            if has_text == "切换账号" and "切换账号" in self.html:
                return FakeLocator(count=1)
            return FakeLocator()
        if selector == "[title='切换账号']":
            return FakeLocator(count=1 if 'title="切换账号"' in self.html else 0)
        if selector == "#js_iframe":
            return FakeLocator(count=1 if 'id="js_iframe"' in self.html else 0)
        if selector == "iframe[src*='gameFeedback']":
            return FakeLocator(count=1 if "gameFeedback" in self.html else 0)
        return FakeLocator()

    def get_by_text(self, text, exact=False):
        if exact and text in self.html:
            return FakeLocator(count=1)
        return FakeLocator()


class FetcherTestBase(unittest.TestCase):
    def tearDown(self):
        close_all_group_runtimes()

    def read_fixture(self, name: str) -> str:
        return (FIXTURE_ROOT / name).read_text(encoding="utf-8")


__all__ = [
    "asyncio",
    "json",
    "unittest",
    "Path",
    "TemporaryDirectory",
    "patch",
    "PlaywrightTimeoutError",
    "extract_current_account_name",
    "fetch_account",
    "fetch_accounts_batch",
    "fetch_switchable_accounts",
    "renew_account_state",
    "save_login_state",
    "save_login_state_with_profile",
    "validate_account_state",
    "wait_for_current_account_name",
    "wait_for_switch_account_items",
    "register_response_capture",
    "fetch_account_in_page_impl",
    "resolve_bootstrap_url",
    "close_all_group_runtimes",
    "CancelledError",
    "_capture_response_payload",
    "_close_context_and_browser",
    "_fallback_from_responses",
    "analyze_storage_state",
    "build_feedback_url",
    "business_iframe_selector",
    "classify_refund_response_type",
    "extract_response_token",
    "is_login_timeout_page",
    "is_wechat_mp_root_page_url",
    "persist_storage_state",
    "recover_login_timeout_page",
    "recover_wechat_mp_root_page",
    "safe_page_content",
    "wait_for_iframe_ready",
    "wait_for_url_contains",
    "wait_or_cancel",
    "find_switch_entry",
    "prepare_switch_account_page",
    "should_retry_switch_from_home",
    "should_switch_account",
    "should_switch_for_account",
    "wait_for_account_switch_stable",
    "AccountConfig",
    "FetchResult",
    "build_notification_summary",
    "filter_target_unread_notifications",
    "extract_labeled_datetime",
    "FIXTURE_ROOT",
    "FakeElementHandle",
    "FakeFrame",
    "FakeLocator",
    "FakePage",
    "FakeResponse",
    "FixturePage",
    "FetcherTestBase",
]
