from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.sync_api import Page

from desktop_py.core.fetcher_common import CancelCheck, CancelledError, Logger, WaitOrCancel, _page_is_closed
from desktop_py.core.models import AccountConfig
from desktop_py.core.page_waiting import wait_or_cancel
from desktop_py.core.store import validate_shared_browser_profile_dir

STORAGE_STATE_RETRY_DELAYS_MS = (1000, 2000)
STORAGE_STATE_SETTLE_MS = 1200
DEFAULT_SESSION_DOMAIN_KEYWORDS = ("mp.weixin.qq.com", "weixin.qq.com")


@dataclass(frozen=True)
class StorageStateSaveResult:
    attempts: int
    indexed_db: bool = True
    fallback_verified: bool = False


@dataclass(frozen=True)
class SessionHealthReport:
    state_path: str
    exists: bool
    readable: bool
    cookies_count: int = 0
    origins_count: int = 0
    matched_cookies_count: int = 0
    session_cookies_count: int = 0
    expired_cookies_count: int = 0
    min_cookie_expires_at: float | None = None
    min_cookie_seconds_remaining: int | None = None
    has_indexed_db: bool = False
    reason: str = ""

    @property
    def has_reusable_state(self) -> bool:
        return self.exists and self.readable and (self.cookies_count > 0 or self.origins_count > 0)

    @property
    def has_expiring_cookie(self) -> bool:
        return self.min_cookie_seconds_remaining is not None


def _cookie_matches_domain(cookie: dict[str, Any], domain_keywords: tuple[str, ...]) -> bool:
    domain = str(cookie.get("domain", "")).lstrip(".").lower()
    return any(keyword.lower() in domain for keyword in domain_keywords)


def _cookie_expires_at(cookie: dict[str, Any]) -> float | None:
    try:
        expires = float(cookie.get("expires", -1))
    except TypeError, ValueError:
        return None
    if expires <= 0:
        return None
    return expires


def _origins_have_indexed_db(origins: list[object]) -> bool:
    return any(isinstance(origin, dict) and bool(origin.get("indexedDB")) for origin in origins)


def analyze_storage_state(
    state_path: str,
    *,
    domain_keywords: tuple[str, ...] = DEFAULT_SESSION_DOMAIN_KEYWORDS,
    now_seconds: float | None = None,
) -> SessionHealthReport:
    target = Path(state_path)
    if not target.exists():
        return SessionHealthReport(str(target), exists=False, readable=False, reason="登录态文件不存在")

    try:
        payload = json.loads(target.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return SessionHealthReport(str(target), exists=True, readable=False, reason=f"登录态文件无法读取：{exc}")

    if not isinstance(payload, dict):
        return SessionHealthReport(str(target), exists=True, readable=False, reason="登录态文件格式不是 JSON 对象")

    raw_cookies = payload.get("cookies", [])
    raw_origins = payload.get("origins", [])
    cookies = [cookie for cookie in raw_cookies if isinstance(cookie, dict)] if isinstance(raw_cookies, list) else []
    origins = raw_origins if isinstance(raw_origins, list) else []
    matched_cookies = [cookie for cookie in cookies if _cookie_matches_domain(cookie, domain_keywords)]
    now = time.time() if now_seconds is None else now_seconds
    expiring_values = [expires for cookie in matched_cookies if (expires := _cookie_expires_at(cookie)) is not None]
    session_cookies_count = len(matched_cookies) - len(expiring_values)
    expired_cookies_count = sum(1 for expires in expiring_values if expires <= now)
    min_cookie_expires_at = min(expiring_values) if expiring_values else None
    min_cookie_seconds_remaining = int(min_cookie_expires_at - now) if min_cookie_expires_at is not None else None

    if not cookies and not origins:
        reason = "登录态文件不包含 Cookie 或 Origin 存储"
    elif not matched_cookies:
        reason = "未找到微信后台相关 Cookie"
    elif expired_cookies_count:
        reason = "存在已过期的微信后台 Cookie"
    elif min_cookie_seconds_remaining is not None:
        reason = f"微信后台 Cookie 最短剩余 {min_cookie_seconds_remaining} 秒"
    else:
        reason = "微信后台 Cookie 为会话 Cookie，无法从文件判断服务端剩余时长"

    return SessionHealthReport(
        str(target),
        exists=True,
        readable=True,
        cookies_count=len(cookies),
        origins_count=len(origins),
        matched_cookies_count=len(matched_cookies),
        session_cookies_count=session_cookies_count,
        expired_cookies_count=expired_cookies_count,
        min_cookie_expires_at=min_cookie_expires_at,
        min_cookie_seconds_remaining=min_cookie_seconds_remaining,
        has_indexed_db=_origins_have_indexed_db(origins),
        reason=reason,
    )


def _wait_or_sleep(
    page: Page | None,
    timeout_ms: int,
    *,
    wait_or_cancel_fn: WaitOrCancel,
    is_cancelled: CancelCheck | None = None,
) -> None:
    if _page_is_closed(page):
        page = None
    if page is not None:
        if callable(getattr(page, "wait_for_timeout", None)):
            wait_or_cancel_fn(page, timeout_ms, is_cancelled)
        return
    if is_cancelled is not None and is_cancelled():
        raise CancelledError("任务已取消")
    time.sleep(timeout_ms / 1000)
    if is_cancelled is not None and is_cancelled():
        raise CancelledError("任务已取消")


def _wait_for_storage_state_ready(
    page: Page | None,
    *,
    wait_or_cancel_fn: WaitOrCancel,
    is_cancelled: CancelCheck | None = None,
    settle_ms: int = STORAGE_STATE_SETTLE_MS,
) -> None:
    if _page_is_closed(page):
        return
    assert page is not None
    try:
        page.wait_for_load_state("domcontentloaded", timeout=1500)
    except Exception:
        pass
    try:
        page.wait_for_load_state("networkidle", timeout=1500)
    except Exception:
        pass
    _wait_or_sleep(page, settle_ms, wait_or_cancel_fn=wait_or_cancel_fn, is_cancelled=is_cancelled)


def _is_indexed_db_serialization_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "indexeddb" in message and (
        "unable to serialize" in message or "internal error" in message or "storage_state" in message
    )


def persist_storage_state(
    context: Any,
    state_path: str,
    *,
    page: Page | None = None,
    logger: Logger | None = None,
    log_fn: Callable[[Logger | None, str], None] | None = None,
    wait_or_cancel_fn: WaitOrCancel = wait_or_cancel,
    is_cancelled: CancelCheck | None = None,
    retry_delays_ms: tuple[int, ...] = STORAGE_STATE_RETRY_DELAYS_MS,
    fallback_verify_fn: Callable[[str], bool] | None = None,
) -> StorageStateSaveResult:
    target = Path(state_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if _page_is_closed(page):
        page = None
    total_attempts = len(retry_delays_ms) + 1
    last_error: Exception | None = None

    for attempt in range(1, total_attempts + 1):
        if attempt > 1:
            delay_ms = retry_delays_ms[attempt - 2]
            if log_fn is not None:
                log_fn(
                    logger,
                    f"登录态保存重试 {attempt}/{total_attempts}：IndexedDB 序列化失败，等待 {delay_ms} ms 后重试。",
                )
            _wait_or_sleep(page, delay_ms, wait_or_cancel_fn=wait_or_cancel_fn, is_cancelled=is_cancelled)

        _wait_for_storage_state_ready(page, wait_or_cancel_fn=wait_or_cancel_fn, is_cancelled=is_cancelled)
        try:
            context.storage_state(path=str(target), indexed_db=True)
            if attempt > 1 and log_fn is not None:
                log_fn(logger, f"登录态保存已在第 {attempt} 次尝试后成功。")
            return StorageStateSaveResult(attempts=attempt)
        except Exception as exc:
            last_error = exc
            if attempt >= total_attempts or not _is_indexed_db_serialization_error(exc):
                if attempt >= total_attempts and _is_indexed_db_serialization_error(exc) and fallback_verify_fn:
                    if log_fn is not None:
                        log_fn(logger, "IndexedDB 序列化持续失败，尝试降级保存 Cookie/LocalStorage 并复验登录态。")
                    temp_path = target.with_name(f".{target.name}.fallback.tmp")
                    try:
                        context.storage_state(path=str(temp_path), indexed_db=False)
                        if fallback_verify_fn(str(temp_path)):
                            os.replace(str(temp_path), str(target))
                            if log_fn is not None:
                                log_fn(logger, "降级登录态已通过复验并保存。")
                            return StorageStateSaveResult(
                                attempts=attempt,
                                indexed_db=False,
                                fallback_verified=True,
                            )
                    finally:
                        try:
                            temp_path.unlink(missing_ok=True)
                        except OSError:
                            pass
                raise

    if last_error is not None:
        raise last_error
    return StorageStateSaveResult(attempts=total_attempts)


def create_browser_context(
    playwright: Any,
    account: AccountConfig,
    headless: bool,
    profile_dir: str = "",
) -> tuple[Any | None, Any]:
    normalized_profile_dir = validate_shared_browser_profile_dir(profile_dir) if profile_dir.strip() else ""
    if normalized_profile_dir:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=normalized_profile_dir,
            headless=headless,
            viewport={"width": 1440, "height": 1200},
        )
        return None, context

    browser = playwright.chromium.launch(headless=headless)
    context = browser.new_context(storage_state=str(account.state_path), viewport={"width": 1440, "height": 1200})
    return browser, context


def _close_page(page: Any) -> None:
    close = getattr(page, "close", None)
    if callable(close):
        close()


def _close_context_and_browser(
    context: Any,
    browser: Any,
    state_path: Path | None = None,
    persist_state: bool = False,
    page: Page | None = None,
    logger: Logger | None = None,
    log_fn: Callable[[Logger | None, str], None] | None = None,
    wait_or_cancel_fn: WaitOrCancel = wait_or_cancel,
    is_cancelled: CancelCheck | None = None,
) -> None:
    context_error: Exception | None = None
    if persist_state and state_path is not None:
        try:
            persist_storage_state(
                context,
                str(state_path),
                page=page,
                logger=logger,
                log_fn=log_fn,
                wait_or_cancel_fn=wait_or_cancel_fn,
                is_cancelled=is_cancelled,
            )
        except Exception as exc:
            context_error = exc

    try:
        context.close()
    except Exception as exc:
        if context_error is None:
            context_error = exc

    browser_error: Exception | None = None
    if browser:
        try:
            browser.close()
        except Exception as exc:
            browser_error = exc

    if context_error is not None:
        raise context_error
    if browser_error is not None:
        raise browser_error
