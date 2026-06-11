from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from desktop_py.core.fetcher_common import CancelCheck, Logger, _wait_for_timeout
from desktop_py.core.fetcher_rules import DEFAULT_NOTIFICATION_RULES, match_notification_title
from desktop_py.core.fetcher_support import (
    FetchError,
    FetchErrorCode,
    fetch_error_code,
    guarded_page_goto,
    is_login_timeout_page,
    recover_login_timeout_page,
)
from desktop_py.core.models import AccountConfig
from desktop_py.core.store import write_account_output_json, write_account_output_text

NOTIFICATION_CENTER_URL_KEYWORD = DEFAULT_NOTIFICATION_RULES.center_url_keyword
NOTIFICATION_CONTAINER_SELECTOR = DEFAULT_NOTIFICATION_RULES.container_selector
NOTIFICATION_ITEM_SELECTOR = DEFAULT_NOTIFICATION_RULES.item_selector
NOTIFICATION_ENTRY_TEXT = DEFAULT_NOTIFICATION_RULES.entry_text
NOTIFICATION_MARK_ALL_READ_SELECTOR = "a.notification_header_read"
TARGET_NOTIFICATION_RULES = DEFAULT_NOTIFICATION_RULES.target_titles

LogFn = Callable[[Logger | None, str], None]


def collect_notification_items(page: Any) -> list[dict[str, Any]]:
    locator = page.locator(NOTIFICATION_ITEM_SELECTOR)
    if locator.count() == 0:
        return []
    items = locator.evaluate_all(
        """
        elements => elements.map(el => ({
          notify_id: (el.getAttribute('notify_id') || '').trim(),
          class_name: (el.className || '').trim(),
          title: (el.querySelector('.notice_title')?.textContent || '').trim(),
          time_text: (el.querySelector('.notice_time')?.textContent || '').trim(),
          content_text: (el.querySelector('dd')?.textContent || '').trim()
        }))
        """
    )
    return [cast(dict[str, Any], item) for item in items if isinstance(item, dict)]


def filter_target_unread_notifications(items: list[dict[str, Any]], account_name: str) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    for item in items:
        class_name = str(item.get("class_name", "") or "").strip()
        if "readed" in class_name:
            continue
        title = str(item.get("title", "") or "").strip()
        if not title:
            continue
        match = match_notification_title(title)
        if match.matched:
            matched.append(
                {
                    "account_name": account_name,
                    "notify_id": str(item.get("notify_id", "") or "").strip(),
                    "title": title,
                    "time_text": str(item.get("time_text", "") or "").strip(),
                    "content_text": str(item.get("content_text", "") or "").strip(),
                    "is_unread": True,
                    "matched_rule": match.rule_name,
                    "rule_version": match.rule_version,
                }
            )
    return matched


def build_notification_summary(notifications: list[dict[str, Any]]) -> str:
    if not notifications:
        return "通知中心无目标未读消息。"
    titles = "、".join(str(item["title"]) for item in notifications[:3] if item.get("title"))
    suffix = " 等" if len(notifications) > 3 else ""
    return f"通知中心未读消息 {len(notifications)} 条：{titles}{suffix}"


def _locator_count(locator: Any) -> int:
    try:
        return int(locator.count())
    except Exception:
        return 0


def _click_locator(locator: Any, timeout_ms: int) -> None:
    try:
        locator.first.click(timeout=timeout_ms)
    except Exception:
        locator.first.evaluate("e => e.click()")


def _is_mark_all_read_response(response: Any) -> bool:
    url = str(getattr(response, "url", "") or "").lower()
    return (
        "wasysnotify" in url
        and ("action%3dupdate" in url or "action=update" in url)
        and ("all%3d1" in url or "all=1" in url)
    )


def _notification_items_all_read(page: Any) -> bool:
    locator = page.locator(NOTIFICATION_ITEM_SELECTOR)
    if _locator_count(locator) == 0:
        return True
    class_names = locator.evaluate_all("elements => elements.map(el => el.className || '')")
    return all("readed" in str(class_name) for class_name in class_names)


def _wait_for_notifications_read_state(page: Any, timeout_ms: int = 5000, interval_ms: int = 200) -> bool:
    deadline = time.monotonic() + timeout_ms / 1000
    while True:
        if _notification_items_all_read(page):
            return True
        if time.monotonic() >= deadline:
            return False
        page.wait_for_timeout(interval_ms)


def mark_all_notifications_read(page: Any, notifications: list[dict[str, Any]]) -> bool:
    if not notifications:
        return False
    action = page.locator(NOTIFICATION_MARK_ALL_READ_SELECTOR)
    if _locator_count(action) == 0:
        for text in ("全部已读", "全部标为已读", "标记全部已读"):
            action = page.get_by_text(text, exact=False)
            if _locator_count(action) > 0:
                break
        else:
            return False

    expect_response = getattr(page, "expect_response", None)
    if callable(expect_response):
        clicked = False
        try:
            with expect_response(_is_mark_all_read_response, timeout=8000):
                _click_locator(action, 3000)
                clicked = True
        except Exception:
            if not clicked:
                _click_locator(action, 3000)
    else:
        _click_locator(action, 3000)

    try:
        page.wait_for_load_state("networkidle", timeout=4000)
    except Exception:
        pass
    return _wait_for_notifications_read_state(page)


def open_notification_center(
    page: Any,
    *,
    account: AccountConfig,
    logger: Logger | None,
    log_fn: LogFn,
    wait_for_url_contains_fn: Callable[..., Any],
    safe_page_content_fn: Callable[..., str],
    is_cancelled: CancelCheck | None = None,
) -> None:
    guarded_page_goto(page, account.home_url, wait_until="domcontentloaded", timeout=60000)
    wait_for_url_contains_fn(page, ("token=", "/wxamp/index/index"), timeout_ms=4000, is_cancelled=is_cancelled)
    if is_login_timeout_page(page, safe_page_content_fn=safe_page_content_fn):
        recover_login_timeout_page(
            page,
            logger=logger,
            log_fn=log_fn,
            safe_page_content_fn=safe_page_content_fn,
            wait_or_cancel_fn=_wait_for_timeout,
            is_cancelled=is_cancelled,
        )
        wait_for_url_contains_fn(page, ("token=", "/wxamp/index/index"), timeout_ms=4000, is_cancelled=is_cancelled)

    entry = page.get_by_text(NOTIFICATION_ENTRY_TEXT, exact=False)
    if entry.count() == 0:
        raise FetchError(
            "未找到通知中心入口。",
            code=FetchErrorCode.NOTIFICATION_ENTRY_MISSING,
            evidence=[
                {
                    "kind": "page",
                    "label": "通知中心入口",
                    "summary": "后台页面未出现通知中心入口文本。",
                    "metadata": {"page_url": str(getattr(page, "url", "") or "")},
                }
            ],
        )
    try:
        entry.first.click(timeout=2000)
    except Exception:
        entry.first.evaluate("e => e.click()")
    try:
        page.wait_for_load_state("networkidle", timeout=6000)
    except Exception:
        pass
    if NOTIFICATION_CENTER_URL_KEYWORD not in page.url and page.locator(NOTIFICATION_CONTAINER_SELECTOR).count() == 0:
        raise FetchError(
            "进入通知中心失败。",
            code=FetchErrorCode.NOTIFICATION_CENTER_OPEN_FAILED,
            evidence=[
                {
                    "kind": "page",
                    "label": "通知中心页面",
                    "summary": "点击入口后未进入通知中心页面，也未发现通知容器。",
                    "metadata": {"page_url": str(getattr(page, "url", "") or "")},
                }
            ],
        )


def fetch_notifications(
    page: Any,
    *,
    account: AccountConfig,
    logger: Logger | None,
    output_dir: Path,
    log_fn: LogFn,
    wait_for_url_contains_fn: Callable[..., Any],
    safe_page_content_fn: Callable[..., str],
    is_cancelled: CancelCheck | None = None,
) -> dict[str, Any]:
    try:
        open_notification_center(
            page,
            account=account,
            logger=logger,
            log_fn=log_fn,
            wait_for_url_contains_fn=wait_for_url_contains_fn,
            safe_page_content_fn=safe_page_content_fn,
            is_cancelled=is_cancelled,
        )
        items = collect_notification_items(page)
        notifications = filter_target_unread_notifications(items, account.name)
        write_account_output_json(account.name, "notifications.json", notifications)
        summary = build_notification_summary(notifications)
        mark_all_notifications_read(page, notifications)
        return {
            "ok": True,
            "notifications": notifications,
            "summary": summary,
            "page_url": page.url,
        }
    except Exception as exc:
        try:
            write_account_output_text(account.name, "notification_page.html", safe_page_content_fn(page))
        except Exception:
            pass
        write_account_output_json(account.name, "notifications.json", [])
        message = f"通知中心抓取失败：{exc}"
        return {
            "ok": False,
            "notifications": [],
            "summary": message,
            "page_url": page.url,
            "error_code": fetch_error_code(exc),
        }
