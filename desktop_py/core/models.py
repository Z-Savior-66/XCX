from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

SESSION_STATUS_MISSING = "missing"
SESSION_STATUS_VALID = "valid"
SESSION_STATUS_STALE = "stale"
SESSION_STATUS_EXPIRED = "expired"
SESSION_STATUS_NEEDS_RELOGIN = "needs_relogin"

SESSION_SOURCE_STATE_FILE = "state_file"
SESSION_SOURCE_PROFILE = "profile"
CONFIG_SCHEMA_VERSION = 1


@dataclass
class AccountConfig:
    name: str
    state_path: str
    schema_version: int = CONFIG_SCHEMA_VERSION
    is_entry_account: bool = True
    feedback_url: str = ""
    home_url: str = "https://mp.weixin.qq.com/"
    enabled: bool = True
    last_login_at: str = ""
    last_fetch_at: str = ""
    last_deadline: str = ""
    last_status: str = ""
    last_note: str = ""
    session_status: str = SESSION_STATUS_MISSING
    session_source: str = ""
    last_session_verified_at: str = ""
    last_session_renewed_at: str = ""
    last_session_error: str = ""
    last_actual_account_name: str = ""
    session_renewal_failures: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AppSettings:
    schema_version: int = CONFIG_SCHEMA_VERSION
    feishu_webhook: str = ""
    login_wait_seconds: int = 120
    headless_fetch: bool = True
    browser_profile_dir: str = ""
    current_main_account_name: str = ""
    auto_fetch_push_enabled: bool = False
    startup_enabled: bool = False
    diagnostic_retention_days: int = 14
    next_auto_renew_at: str = ""
    next_auto_fetch_push_at: str = ""
    auto_renew_schedule_reason: str = ""
    auto_fetch_push_schedule_reason: str = ""
    schedule_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FetchResult:
    account_name: str
    ok: bool
    actual_account_name: str = ""
    deadline_text: str = ""
    deadline_source: str = ""
    matched_path: str = ""
    page_url: str = ""
    note: str = ""
    fetched_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
