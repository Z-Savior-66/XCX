from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import urlparse

from playwright.sync_api import Page

from desktop_py.core.models import AccountConfig
from desktop_py.core.session_links import canonical_feedback_url, canonical_ios_refund_feedback_url


class FetchErrorCode(StrEnum):
    MISSING_TOKEN = "missing_token"
    SESSION_STATE_INVALID = "session_state_invalid"
    BUSINESS_IFRAME_MISSING = "business_iframe_missing"
    DEADLINE_MISSING = "deadline_missing"
    NOTIFICATION_ENTRY_MISSING = "notification_entry_missing"
    NOTIFICATION_CENTER_OPEN_FAILED = "notification_center_open_failed"
    SWITCH_ENTRY_MISSING = "switch_entry_missing"
    SWITCH_ACCOUNT_NOT_FOUND = "switch_account_not_found"
    SWITCH_ACCOUNT_MISMATCH = "switch_account_mismatch"
    SWITCH_ACCOUNT_LIST_EMPTY = "switch_account_list_empty"
    NETWORK_NAVIGATION_FAILED = "network_navigation_failed"
    TRANSACTION_COMPLAINT_RESPONSE_INVALID = "transaction_complaint_response_invalid"
    TRANSACTION_COMPLAINT_API_FAILED = "transaction_complaint_api_failed"


class FetchError(RuntimeError):
    """抓取失败。"""

    def __init__(
        self,
        message: str,
        *,
        code: FetchErrorCode | str | None = None,
        evidence: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.evidence = list(evidence or [])


class CancelledError(RuntimeError):
    """后台任务已取消。"""


ValidateSharedBrowserProfileDir = Callable[[str], str]
PathExists = Callable[[Path], bool]
CancelCheck = Callable[[], bool]
ExtractCurrentAccountName = Callable[[Page], str]
Logger = Callable[[str], None]
WaitOrCancel = Callable[[Page, int, CancelCheck | None], None]


class SafePageContent(Protocol):
    def __call__(self, page: Page, timeout_ms: int = ...) -> str: ...


def _page_is_closed(page: Page | None) -> bool:
    if page is None:
        return True
    is_closed = getattr(page, "is_closed", None)
    if callable(is_closed):
        try:
            return bool(is_closed())
        except Exception:
            return True
    return False


def normalize_profile_dir(
    profile_dir: str,
    *,
    validate_shared_browser_profile_dir_fn: ValidateSharedBrowserProfileDir,
) -> str:
    if not profile_dir.strip():
        return ""
    return cast(str, validate_shared_browser_profile_dir_fn(profile_dir))


def account_state_path(account: AccountConfig) -> Path:
    return Path(account.state_path)


def ensure_account_session_available(
    account: AccountConfig,
    normalized_profile_dir: str,
    *,
    path_exists_fn: PathExists,
    error_cls: type[Exception] | None = None,
) -> Path | None:
    state_path = account_state_path(account)
    if normalized_profile_dir:
        return state_path
    if path_exists_fn(state_path):
        return state_path
    if error_cls is not None:
        if error_cls is FetchError:
            raise FetchError(
                f"账号 {account.name} 缺少登录态文件：{state_path}",
                code=FetchErrorCode.SESSION_STATE_INVALID,
                evidence=[
                    {
                        "kind": "file",
                        "label": "登录态文件",
                        "path": str(state_path),
                        "summary": "未找到账号登录态文件。",
                    }
                ],
            )
        raise error_cls(f"账号 {account.name} 缺少登录态文件：{state_path}")
    return None


def build_feedback_url(page_url: str) -> str:
    feedback_url = canonical_feedback_url(page_url)
    if not feedback_url:
        raise FetchError(
            "当前后台地址中未找到有效 token，无法自动构造反馈页链接。",
            code=FetchErrorCode.MISSING_TOKEN,
            evidence=[
                {
                    "kind": "page",
                    "label": "当前页面地址",
                    "summary": "构造反馈页链接时未找到 token。",
                    "metadata": {"page_url": page_url},
                }
            ],
        )
    return feedback_url


def build_ios_refund_feedback_url(page_url: str) -> str:
    feedback_url = canonical_ios_refund_feedback_url(page_url)
    if not feedback_url:
        raise FetchError(
            "当前后台地址中未找到有效 token，无法自动构造 iOS 退款问询链接。",
            code=FetchErrorCode.MISSING_TOKEN,
            evidence=[
                {
                    "kind": "page",
                    "label": "当前页面地址",
                    "summary": "构造 iOS 退款问询链接时未找到 token。",
                    "metadata": {"page_url": page_url},
                }
            ],
        )
    return feedback_url


def is_network_navigation_error(error: Exception) -> bool:
    message = str(error).lower()
    tokens = (
        "net::err_name_not_resolved",
        "net::err_internet_disconnected",
        "net::err_connection",
        "net::err_timed_out",
        "net::err_network_changed",
        "net::err_proxy",
        "net::err_tunnel_connection_failed",
        "dns",
    )
    return ("page.goto" in message or "navigating to" in message) and any(token in message for token in tokens)


def guarded_page_goto(page: Page, url: str, *, wait_until: str | None = None, timeout: int | None = None) -> Any:
    kwargs: dict[str, Any] = {}
    if wait_until is not None:
        kwargs["wait_until"] = wait_until
    if timeout is not None:
        kwargs["timeout"] = timeout
    try:
        return page.goto(url, **kwargs)
    except Exception as exc:
        if not is_network_navigation_error(exc):
            raise
        parsed = urlparse(url)
        host = parsed.netloc or url
        raise FetchError(
            f"无法访问微信后台（{host}），请检查网络、DNS 或代理设置后重试。",
            code=FetchErrorCode.NETWORK_NAVIGATION_FAILED,
            evidence=[
                {
                    "kind": "network",
                    "label": "微信后台访问",
                    "summary": "浏览器打开微信后台时发生网络解析或连接失败。",
                    "metadata": {
                        "target_url": url,
                        "host": host,
                        "playwright_error": str(exc),
                    },
                }
            ],
        ) from exc


def fetch_error_code(error: BaseException) -> str:
    code = getattr(error, "code", None)
    if isinstance(code, FetchErrorCode):
        return code.value
    if isinstance(code, str):
        return code.strip()
    return ""


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or default)
    except TypeError, ValueError:
        return default


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _wait_for_timeout(current_page: Any, wait_ms: int, _cancelled: CancelCheck | None = None) -> None:
    current_page.wait_for_timeout(wait_ms)


def _log(logger: Logger | None, message: str) -> None:
    if logger is not None:
        logger(message)
