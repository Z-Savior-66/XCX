from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast

from playwright.sync_api import Page

from desktop_py.core.models import AccountConfig
from desktop_py.core.session_links import canonical_feedback_url


class FetchError(RuntimeError):
    """抓取失败。"""


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
        raise error_cls(f"账号 {account.name} 缺少登录态文件：{state_path}")
    return None


def build_feedback_url(page_url: str) -> str:
    feedback_url = canonical_feedback_url(page_url)
    if not feedback_url:
        raise FetchError("当前后台地址中未找到有效 token，无法自动构造反馈页链接。")
    return feedback_url


def _log(logger: Logger | None, message: str) -> None:
    if logger is not None:
        logger(message)
