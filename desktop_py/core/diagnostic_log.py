from __future__ import annotations

from datetime import datetime
from pathlib import Path

from desktop_py.core.store import LOG_DIR

SESSION_LOG_PREFIX = "login-session"


def session_log_file(*, now: datetime | None = None, log_dir: Path | None = None) -> Path:
    current = now or datetime.now()
    target_dir = log_dir or LOG_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / f"{SESSION_LOG_PREFIX}-{current.strftime('%Y-%m-%d')}.log"


def append_session_log(message: str, *, now: datetime | None = None, log_dir: Path | None = None) -> Path | None:
    current = now or datetime.now()
    path = session_log_file(now=current, log_dir=log_dir)
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"[{current.strftime('%Y-%m-%d %H:%M:%S')}] {message.rstrip()}\n")
    except OSError:
        return None
    return path


def log_session_offline(
    account_name: str,
    reason: str = "",
    *,
    branch: str = "",
    page_url: str = "",
    log_dir: Path | None = None,
) -> Path | None:
    detail = f"账号 {account_name} 登录态掉线"
    session_detail = _session_detail_text(reason, branch, page_url)
    if session_detail:
        detail = f"{detail}：{session_detail}"
    return append_session_log(detail, log_dir=log_dir)


def log_session_renew_failed(
    account_name: str,
    reason: str = "",
    *,
    branch: str = "",
    page_url: str = "",
    log_dir: Path | None = None,
) -> Path | None:
    detail = f"账号 {account_name} 登录态续期失败"
    session_detail = _session_detail_text(reason, branch, page_url)
    if session_detail:
        detail = f"{detail}：{session_detail}"
    return append_session_log(detail, log_dir=log_dir)


def _session_detail_text(reason: str = "", branch: str = "", page_url: str = "") -> str:
    parts: list[str] = []
    if reason.strip():
        parts.append(reason.strip())
    if branch.strip():
        parts.append(f"判定分支={branch.strip()}")
    if page_url.strip():
        parts.append(f"page.url={page_url.strip()}")
    return "；".join(parts)
