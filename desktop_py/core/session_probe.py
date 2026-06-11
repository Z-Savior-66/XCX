from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from desktop_py.core.fetcher_common import Logger, _now_text, _wait_for_timeout, guarded_page_goto
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
from desktop_py.core.page_waiting import (
    is_login_timeout_page,
    is_wechat_mp_root_page_url,
    recover_login_timeout_page,
    recover_wechat_mp_root_page,
    safe_page_content,
)
from desktop_py.core.session_links import canonical_feedback_url

BACKEND_SESSION_URL_KEYWORDS = ("token=", "/wxamp/index/index", "pluginRedirect/gameFeedback")
BACKEND_SESSION_CONTENT_KEYWORDS = (
    '"nickName"',
    "current_login",
    "switch_account_dialog",
    "menu_box_account_info",
    "切换账号",
)
SESSION_STALE_AFTER = timedelta(days=3)
SESSION_TIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M")

LogFn = Callable[[Logger | None, str], None]


@dataclass(frozen=True)
class SessionVerification:
    valid: bool
    status: str = SESSION_STATUS_EXPIRED
    actual_account_name: str = ""
    feedback_url: str = ""
    reason: str = ""
    branch: str = ""
    page_url: str = ""
    should_retry: bool = False
    should_relogin: bool = False
    session_source: str = ""


def session_source_for_profile_dir(profile_dir: str) -> str:
    return SESSION_SOURCE_PROFILE if profile_dir.strip() else SESSION_SOURCE_STATE_FILE


def _parse_datetime(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    for fmt in SESSION_TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _verified_status_for_account(account: AccountConfig | None) -> str:
    if account is None:
        return SESSION_STATUS_VALID
    latest_activity = (
        _parse_datetime(account.last_session_renewed_at)
        or _parse_datetime(account.last_login_at)
        or _parse_datetime(account.last_session_verified_at)
    )
    if latest_activity is None:
        return SESSION_STATUS_VALID
    if datetime.now() - latest_activity >= SESSION_STALE_AFTER:
        return SESSION_STATUS_STALE
    return SESSION_STATUS_VALID


def apply_session_verification(
    account: AccountConfig,
    verification: SessionVerification,
    *,
    profile_dir: str = "",
    verified_at: str | None = None,
    renewed: bool = False,
) -> None:
    timestamp = verified_at or _now_text()
    account.session_status = verification.status
    account.session_source = verification.session_source or session_source_for_profile_dir(profile_dir)
    account.last_session_verified_at = timestamp
    account.last_session_error = "" if verification.valid else verification.reason
    if verification.actual_account_name.strip():
        account.last_actual_account_name = verification.actual_account_name.strip()
    if verification.feedback_url:
        account.feedback_url = verification.feedback_url
    if renewed:
        account.last_session_renewed_at = timestamp


def mark_account_session_missing(account: AccountConfig, *, profile_dir: str = "", reason: str = "") -> None:
    account.session_status = SESSION_STATUS_MISSING
    account.session_source = session_source_for_profile_dir(profile_dir)
    account.last_session_error = reason.strip()


def _has_backend_session_url(page: Any) -> bool:
    return any(keyword in str(getattr(page, "url", "") or "") for keyword in BACKEND_SESSION_URL_KEYWORDS)


def _extract_account_name_from_html(html: str) -> str:
    try:
        matched = re.search(r'"nickName":"([^"]+)"', html)
    except Exception:
        return ""
    if not matched:
        return ""
    return matched.group(1).strip()


def _locator_count(page: Any, selector: str, **kwargs: Any) -> int:
    try:
        return int(page.locator(selector, **kwargs).count())
    except Exception:
        return 0


def _has_backend_session_locator(page: Any) -> bool:
    if not callable(getattr(page, "locator", None)):
        return False
    if _locator_count(page, ".switch_account_dialog .account_item") > 0:
        return True
    if _locator_count(page, "div.menu_box_account_info_item[title='切换账号']") > 0:
        return True
    if _locator_count(page, ".menu_box_account_info_item", has_text="切换账号") > 0:
        return True
    if _locator_count(page, "[title='切换账号']") > 0:
        return True
    try:
        return bool(page.get_by_text("切换账号", exact=True).count() > 0)
    except Exception:
        return False


def _has_backend_session_content(page: Any) -> bool:
    if not callable(getattr(page, "content", None)):
        return False
    if is_login_timeout_page(page, safe_page_content_fn=safe_page_content):
        return False
    try:
        html = safe_page_content(page, timeout_ms=1500)
    except Exception:
        return False
    return any(keyword in html for keyword in BACKEND_SESSION_CONTENT_KEYWORDS)


def verify_backend_session(page: Any, account: AccountConfig | None = None) -> SessionVerification:
    current_url = str(getattr(page, "url", "") or "")
    if is_login_timeout_page(page, safe_page_content_fn=safe_page_content):
        return SessionVerification(
            False,
            status=SESSION_STATUS_EXPIRED,
            reason="页面显示登录超时",
            branch="login_timeout_page",
            page_url=current_url,
            should_relogin=True,
        )

    html = ""
    if callable(getattr(page, "content", None)):
        try:
            html = safe_page_content(page, timeout_ms=2000)
        except Exception:
            html = ""

    actual_account_name = _extract_account_name_from_html(html)
    content_valid = any(keyword in html for keyword in BACKEND_SESSION_CONTENT_KEYWORDS)
    locator_valid = _has_backend_session_locator(page)
    feedback_url = ""
    if _has_backend_session_url(page):
        feedback_url = canonical_feedback_url(current_url)

    if actual_account_name or locator_valid or content_valid:
        return SessionVerification(
            True,
            status=_verified_status_for_account(account),
            actual_account_name=actual_account_name,
            feedback_url=feedback_url,
            reason="后台账号信息校验通过",
            branch="backend_account_signals",
            page_url=current_url,
        )
    if (
        _has_backend_session_url(page)
        and not callable(getattr(page, "content", None))
        and not callable(getattr(page, "locator", None))
    ):
        return SessionVerification(
            True,
            status=_verified_status_for_account(account),
            feedback_url=feedback_url,
            reason="测试页缺少可检查 DOM，按后台 URL 兼容",
            branch="backend_url_without_dom",
            page_url=current_url,
        )
    if _has_backend_session_url(page):
        return SessionVerification(
            False,
            status=SESSION_STATUS_EXPIRED,
            reason="仅检测到后台 URL/token，未检测到账号菜单或账号信息",
            branch="backend_url_without_account_signals",
            page_url=current_url,
            should_retry=True,
        )
    return SessionVerification(
        False,
        status=SESSION_STATUS_NEEDS_RELOGIN,
        reason="未检测到后台账号信息",
        branch="missing_backend_account_signals",
        page_url=current_url,
        should_relogin=True,
    )


def _has_backend_session(page: Any) -> bool:
    return verify_backend_session(page).valid


def _wait_for_backend_session(
    page: Any,
    *,
    wait_for_url_contains_fn: Callable[..., Any],
    timeout_ms: int,
) -> bool:
    try:
        wait_for_url_contains_fn(page, BACKEND_SESSION_URL_KEYWORDS, timeout_ms=timeout_ms)
    except PlaywrightTimeoutError:
        pass
    return _has_backend_session(page)


def _probe_account_session_url(
    page: Any,
    url: str,
    *,
    wait_for_url_contains_fn: Callable[..., Any],
    timeout_ms: int,
) -> bool:
    try:
        guarded_page_goto(page, url, wait_until="domcontentloaded", timeout=60000)
    except PlaywrightTimeoutError:
        if recover_login_timeout_page(
            page,
            safe_page_content_fn=safe_page_content,
            wait_or_cancel_fn=_wait_for_timeout,
        ):
            return _wait_for_backend_session(
                page, wait_for_url_contains_fn=wait_for_url_contains_fn, timeout_ms=timeout_ms
            )
        return _has_backend_session(page)
    if _wait_for_backend_session(page, wait_for_url_contains_fn=wait_for_url_contains_fn, timeout_ms=timeout_ms):
        return True
    if recover_login_timeout_page(
        page,
        safe_page_content_fn=safe_page_content,
        wait_or_cancel_fn=_wait_for_timeout,
    ):
        return _wait_for_backend_session(page, wait_for_url_contains_fn=wait_for_url_contains_fn, timeout_ms=timeout_ms)
    return _has_backend_session(page)


def _probe_account_session(
    page: Any,
    account: AccountConfig,
    *,
    wait_for_url_contains_fn: Callable[..., Any],
    timeout_ms: int,
) -> bool:
    return _probe_account_session_result(
        page,
        account,
        wait_for_url_contains_fn=wait_for_url_contains_fn,
        timeout_ms=timeout_ms,
    ).valid


def _probe_account_candidate_urls(account: AccountConfig, *, prefer_feedback_url: bool = False) -> list[str]:
    urls: list[str] = []
    feedback_url = canonical_feedback_url(account.feedback_url)
    candidates = (feedback_url, account.home_url) if prefer_feedback_url else (account.home_url,)
    for url in candidates:
        value = url.strip()
        if value and value not in urls:
            urls.append(value)
    return urls


def _probe_account_session_result(
    page: Any,
    account: AccountConfig,
    *,
    logger: Logger | None = None,
    log_fn: LogFn | None = None,
    wait_for_url_contains_fn: Callable[..., Any],
    timeout_ms: int,
    prefer_feedback_url: bool = False,
) -> SessionVerification:
    if not callable(getattr(page, "goto", None)):
        return SessionVerification(
            True,
            status=_verified_status_for_account(account),
            reason="兼容测试页：跳过后台导航探测",
            branch="compatibility_page_without_goto",
            page_url=str(getattr(page, "url", "") or ""),
        )

    verification = SessionVerification(
        False,
        status=SESSION_STATUS_MISSING,
        reason="没有可用于探测的后台地址",
        branch="missing_probe_url",
        should_relogin=True,
    )
    for url in _probe_account_candidate_urls(account, prefer_feedback_url=prefer_feedback_url):
        _probe_account_session_url(
            page,
            url,
            wait_for_url_contains_fn=wait_for_url_contains_fn,
            timeout_ms=timeout_ms,
        )
        verification = verify_backend_session(page, account)
        if (
            not verification.valid
            and verification.branch == "missing_backend_account_signals"
            and is_wechat_mp_root_page_url(verification.page_url)
            and recover_wechat_mp_root_page(page, wait_or_cancel_fn=_wait_for_timeout, logger=logger, log_fn=log_fn)
        ):
            _wait_for_backend_session(page, wait_for_url_contains_fn=wait_for_url_contains_fn, timeout_ms=timeout_ms)
            verification = verify_backend_session(page, account)
        if verification.valid:
            return verification
    return verification
