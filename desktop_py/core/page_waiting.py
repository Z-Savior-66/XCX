from __future__ import annotations

import time
from collections.abc import Callable

from playwright.sync_api import Page

from desktop_py.core.fetcher_common import (
    CancelCheck,
    CancelledError,
    ExtractCurrentAccountName,
    Logger,
    SafePageContent,
    WaitOrCancel,
)
from desktop_py.core.fetcher_rules import DEFAULT_REFUND_RULES

BUSINESS_IFRAME_SELECTORS = DEFAULT_REFUND_RULES.iframe_selectors
LOGIN_TIMEOUT_PAGE_TEXT = "登录超时，请重新登录"
LOGIN_TIMEOUT_NAV_TEXT = "小程序"
LOGIN_TIMEOUT_EXIT_TEXT = "退出登录"
MINI_PROGRAM_HOME_SELECTORS = (
    "div:has-text('小程序')",
    "span:has-text('小程序')",
    "a:has-text('小程序')",
    "text=小程序",
)


def wait_for_url_contains(
    page: Page,
    keywords: tuple[str, ...],
    timeout_ms: int = 5000,
    is_cancelled: CancelCheck | None = None,
) -> bool:
    deadline = time.monotonic() + (timeout_ms / 1000)
    while time.monotonic() < deadline:
        current_url = page.url
        if any(keyword in current_url for keyword in keywords):
            return True
        wait_or_cancel(page, 200, is_cancelled)
    return any(keyword in page.url for keyword in keywords)


def wait_for_current_account_name(
    page: Page,
    expected_name: str,
    timeout_ms: int = 5000,
    is_cancelled: CancelCheck | None = None,
    *,
    extract_current_account_name_fn: ExtractCurrentAccountName,
) -> str:
    deadline = time.monotonic() + (timeout_ms / 1000)
    while time.monotonic() < deadline:
        actual_name = str(extract_current_account_name_fn(page)).strip()
        if actual_name and actual_name == expected_name:
            return actual_name
        wait_or_cancel(page, 250, is_cancelled)
    return str(extract_current_account_name_fn(page)).strip()


def business_iframe_selector(page: Page) -> str:
    for selector in BUSINESS_IFRAME_SELECTORS:
        try:
            if page.locator(selector).count() > 0:
                return selector
        except Exception:
            continue
    return ""


def wait_for_iframe_ready(page: Page, timeout_ms: int = 5000, is_cancelled: CancelCheck | None = None) -> bool:
    deadline = time.monotonic() + (timeout_ms / 1000)
    while time.monotonic() < deadline:
        selector = business_iframe_selector(page)
        if not selector:
            wait_or_cancel(page, 200, is_cancelled)
            continue
        iframe = page.locator(selector)
        if iframe.count() > 0:
            try:
                handle = iframe.element_handle()
                if handle is not None:
                    frame = handle.content_frame()
                    if frame is not None and frame.url and frame.url != "about:blank":
                        try:
                            frame.wait_for_load_state("domcontentloaded", timeout=1000)
                        except Exception:
                            pass
                        try:
                            frame.wait_for_load_state("networkidle", timeout=1000)
                        except Exception:
                            pass
                        body = frame.locator("body")
                        body_text = (body.text_content(timeout=500) or "").strip()
                        body_html = (body.inner_html(timeout=500) or "").strip()
                        if any(token in body_text for token in DEFAULT_REFUND_RULES.iframe_ready_markers):
                            return True
                        if any(token in body_html for token in DEFAULT_REFUND_RULES.iframe_ready_markers):
                            return True
                        if body_text and not body_text.startswith("document.getElementById("):
                            return True
            except Exception:
                pass
        wait_or_cancel(page, 200, is_cancelled)
    return False


def wait_or_cancel(page: Page, timeout_ms: int, is_cancelled: CancelCheck | None = None) -> None:
    if is_cancelled is not None and is_cancelled():
        raise CancelledError("任务已取消")
    page.wait_for_timeout(timeout_ms)
    if is_cancelled is not None and is_cancelled():
        raise CancelledError("任务已取消")


def _page_contains_text(page: Page, text: str, *, safe_page_content_fn: SafePageContent) -> bool:
    try:
        html = safe_page_content_fn(page, timeout_ms=1500)
    except Exception:
        html = ""
    if text in html:
        return True
    try:
        return page.locator(f"text={text}").count() > 0
    except Exception:
        return False


def is_login_timeout_page(page: Page, *, safe_page_content_fn: SafePageContent) -> bool:
    if not _page_contains_text(page, LOGIN_TIMEOUT_PAGE_TEXT, safe_page_content_fn=safe_page_content_fn):
        return False
    return _page_contains_text(
        page, LOGIN_TIMEOUT_NAV_TEXT, safe_page_content_fn=safe_page_content_fn
    ) or _page_contains_text(page, LOGIN_TIMEOUT_EXIT_TEXT, safe_page_content_fn=safe_page_content_fn)


def recover_login_timeout_page(
    page: Page,
    *,
    safe_page_content_fn: SafePageContent,
    wait_or_cancel_fn: WaitOrCancel,
    logger: Logger | None = None,
    log_fn: Callable[[Logger | None, str], None] | None = None,
    is_cancelled: CancelCheck | None = None,
) -> bool:
    if not is_login_timeout_page(page, safe_page_content_fn=safe_page_content_fn):
        return False

    if log_fn is not None:
        log_fn(logger, "检测到后台登录超时页，尝试点击左上角“小程序”恢复。")

    for selector in MINI_PROGRAM_HOME_SELECTORS:
        try:
            target = page.locator(selector)
            if target.count() == 0:
                continue
            try:
                target.first.click(timeout=1000)
            except Exception:
                target.first.evaluate("e => e.click()")
            break
        except Exception:
            continue
    else:
        if log_fn is not None:
            log_fn(logger, "后台登录超时页恢复失败：未找到左上角“小程序”入口。")
        return False

    for _ in range(15):
        wait_or_cancel_fn(page, 300, is_cancelled)
        if not is_login_timeout_page(page, safe_page_content_fn=safe_page_content_fn):
            if log_fn is not None:
                log_fn(logger, "后台登录超时页恢复成功。")
            return True

    if log_fn is not None:
        log_fn(logger, "后台登录超时页恢复失败：点击“小程序”后页面仍停留在超时提示。")
    return False


def _is_navigation_content_error(error: Exception) -> bool:
    message = str(error).lower()
    return "page.content" in message and ("navigating" in message or "changing the content" in message)


def safe_page_content(page: Page, timeout_ms: int = 3000) -> str:
    deadline = time.monotonic() + (timeout_ms / 1000)
    last_error = None
    try:
        page.wait_for_load_state("domcontentloaded", timeout=min(timeout_ms, 1500))
    except Exception:
        pass
    while time.monotonic() < deadline:
        try:
            return page.content()
        except Exception as exc:
            last_error = exc
            if _is_navigation_content_error(exc):
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=1000)
                except Exception:
                    pass
                try:
                    page.wait_for_load_state("networkidle", timeout=1000)
                except Exception:
                    pass
                page.wait_for_timeout(300)
                continue
            page.wait_for_timeout(200)
    if last_error is not None:
        raise last_error
    return page.content()
