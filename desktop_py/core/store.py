from __future__ import annotations

import json
import os
import stat
import sys
import time
from collections.abc import Callable
from dataclasses import fields
from pathlib import Path
from typing import Any, cast

from desktop_py.core.app_lock import (
    AppInstanceLock,
    RUNNING_INSTANCE_LOCK_STALE_SECONDS,
    acquire_app_instance_lock as _acquire_app_instance_lock_impl,
)
from desktop_py.core.file_io import (
    _backup_corrupt_json_file,
    _read_json_file_or_recover,
    _write_text_atomic,
    read_json_file,
)
from desktop_py.core.models import AccountConfig, AppSettings, FetchResult, ScheduleState
from desktop_py.core.profile_validation import (
    BROWSER_PROFILE_LOCK_FILES,
    SHARED_BROWSER_PROFILE_DIR_NAME,
    prepare_shared_browser_profile_dir,
    validate_shared_browser_profile_dir,
)

APP_NAME = "小程序工具"
ATOMIC_WRITE_REPLACE_ATTEMPTS = 5
ATOMIC_WRITE_RETRY_DELAY_SECONDS = 0.1


def runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        executable_dir = Path(sys.executable).resolve().parent
        if os.access(executable_dir, os.W_OK):
            return executable_dir
        local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
        if local_appdata:
            return Path(local_appdata).expanduser() / APP_NAME
        return executable_dir
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = runtime_root()
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = DATA_DIR / "logs"
STORAGE_DIR = PROJECT_ROOT / "storage"
PY_OUTPUT_DIR = PROJECT_ROOT / "output" / "desktop_py"
ACCOUNTS_FILE = DATA_DIR / "accounts.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
SCHEDULE_STATE_FILE = DATA_DIR / "schedule_state.json"
RUNNING_INSTANCE_LOCK_FILE = DATA_DIR / "app.lock"
BLOCKED_ACCOUNTS_FILE = Path(__file__).resolve().parent / "blocked_accounts.json"
DEFAULT_BLOCKED_ACCOUNT_NAMES = (
    "山每北荒修僊1",
    "山每北荒修僊2",
    "山每北荒修僊4",
    "叨空SSR",
)
DEFAULT_BLOCKED_ACCOUNTS_CONTENT = json.dumps(list(DEFAULT_BLOCKED_ACCOUNT_NAMES), ensure_ascii=False, indent=2) + "\n"
DIAGNOSTIC_INDEX_FILE = PY_OUTPUT_DIR / "diagnostic_index.json"
DIAGNOSTIC_ARTIFACT_NAMES = frozenset(
    {
        "fetch_manifest.json",
        "page.html",
        "iframe.html",
        "iframe.txt",
        "responses.json",
    }
)


def acquire_app_instance_lock(
    *,
    lock_path: Path = RUNNING_INSTANCE_LOCK_FILE,
    stale_seconds: int = RUNNING_INSTANCE_LOCK_STALE_SECONDS,
    process_id_fn: Callable[[], int] = os.getpid,
    process_running_fn: Callable[[int], bool] | None = None,
    now_fn: Callable[[], float] = time.time,
) -> AppInstanceLock:
    kwargs: dict[str, Any] = {
        "lock_path": lock_path,
        "stale_seconds": stale_seconds,
        "process_id_fn": process_id_fn,
        "now_fn": now_fn,
        "ensure_dirs_fn": ensure_runtime_dirs,
    }
    if process_running_fn is not None:
        kwargs["process_running_fn"] = process_running_fn
    return _acquire_app_instance_lock_impl(**kwargs)


def ensure_runtime_dirs() -> None:
    for dir_path in (DATA_DIR, LOG_DIR, STORAGE_DIR, PY_OUTPUT_DIR):
        dir_path.mkdir(parents=True, exist_ok=True)
        try:
            dir_path.chmod(stat.S_IRWXU)
        except OSError:
            pass
    if not ACCOUNTS_FILE.exists():
        _write_text_atomic(ACCOUNTS_FILE, "[]\n")
    if not SETTINGS_FILE.exists():
        _write_text_atomic(SETTINGS_FILE, json.dumps(AppSettings().to_dict(), ensure_ascii=False, indent=2) + "\n")


def load_accounts() -> list[AccountConfig]:
    ensure_runtime_dirs()
    data = cast(list[dict[str, Any]], _read_json_file_or_recover(ACCOUNTS_FILE, "[]\n"))
    allowed = {item.name for item in fields(AccountConfig)}
    return [AccountConfig(**{key: value for key, value in item.items() if key in allowed}) for item in data]


def save_accounts(accounts: list[AccountConfig]) -> None:
    ensure_runtime_dirs()
    _write_text_atomic(
        ACCOUNTS_FILE, json.dumps([account.to_dict() for account in accounts], ensure_ascii=False, indent=2) + "\n"
    )


def load_settings() -> AppSettings:
    ensure_runtime_dirs()
    default_content = json.dumps(AppSettings().to_dict(), ensure_ascii=False, indent=2) + "\n"
    raw = cast(dict[str, Any], _read_json_file_or_recover(SETTINGS_FILE, default_content))
    allowed = {item.name for item in fields(AppSettings)}
    filtered = {key: value for key, value in raw.items() if key in allowed}
    return AppSettings(**filtered)


def save_settings(settings: AppSettings) -> None:
    ensure_runtime_dirs()
    _write_text_atomic(SETTINGS_FILE, json.dumps(settings.to_dict(), ensure_ascii=False, indent=2) + "\n")


def _schedule_state_from_mapping(raw: dict[str, Any]) -> ScheduleState:
    allowed = {item.name for item in fields(ScheduleState)}
    filtered = {key: value for key, value in raw.items() if key in allowed}
    return ScheduleState(**filtered)


def _legacy_schedule_state_from_settings() -> ScheduleState:
    try:
        raw = read_json_file(SETTINGS_FILE)
    except (OSError, json.JSONDecodeError):
        return ScheduleState()
    if not isinstance(raw, dict):
        return ScheduleState()
    return _schedule_state_from_mapping(raw)


def load_schedule_state() -> ScheduleState:
    ensure_runtime_dirs()
    default_content = json.dumps(ScheduleState().to_dict(), ensure_ascii=False, indent=2) + "\n"
    if not SCHEDULE_STATE_FILE.exists():
        state = _legacy_schedule_state_from_settings()
        _write_text_atomic(SCHEDULE_STATE_FILE, json.dumps(state.to_dict(), ensure_ascii=False, indent=2) + "\n")
        return state
    raw = cast(dict[str, Any], _read_json_file_or_recover(SCHEDULE_STATE_FILE, default_content))
    if not isinstance(raw, dict):
        return ScheduleState()
    return _schedule_state_from_mapping(raw)


def save_schedule_state(state: ScheduleState) -> None:
    ensure_runtime_dirs()
    _write_text_atomic(SCHEDULE_STATE_FILE, json.dumps(state.to_dict(), ensure_ascii=False, indent=2) + "\n")


def account_state_path(name: str) -> str:
    safe_name = "".join(char if char.isalnum() else "_" for char in name).strip("_") or "account"
    return str(STORAGE_DIR / f"{safe_name}.json")


def default_state_path(accounts: list[AccountConfig]) -> str:
    for account in accounts:
        if account.state_path:
            return account.state_path
    return str(STORAGE_DIR / "shared_accounts.json")


def account_output_dir(account_name: str) -> Path:
    safe_name = "".join(char if char.isalnum() else "_" for char in account_name).strip("_") or "account"
    target = PY_OUTPUT_DIR / safe_name
    target.mkdir(parents=True, exist_ok=True)
    return target


def account_output_file(account_name: str, filename: str) -> Path:
    if ".." in filename or "/" in filename or "\\" in filename:
        raise ValueError(f"文件名包含非法字符：{filename}")
    return account_output_dir(account_name) / filename


def write_account_output_text(account_name: str, filename: str, content: str) -> None:
    _write_text_atomic(account_output_file(account_name, filename), content)


def write_account_output_json(account_name: str, filename: str, payload: object) -> None:
    _write_text_atomic(
        account_output_file(account_name, filename), json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    )


def diagnostic_index_file() -> Path:
    PY_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return DIAGNOSTIC_INDEX_FILE


def write_diagnostic_index_json(payload: object) -> Path:
    target = diagnostic_index_file()
    _write_text_atomic(target, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return target


def write_fetch_result(account_name: str, result: FetchResult, extra: dict | None = None) -> None:
    payload = result.to_dict()
    if extra:
        payload["extra"] = extra
    write_account_output_json(account_name, "result.json", payload)


def cleanup_account_diagnostics(account_name: str, *, retention_days: int = 14) -> int:
    if retention_days <= 0:
        return 0
    account_dir = account_output_dir(account_name)
    cutoff = time.time() - retention_days * 24 * 60 * 60
    removed = 0
    for path in account_dir.iterdir():
        if not path.is_file() or path.name not in DIAGNOSTIC_ARTIFACT_NAMES:
            continue
        try:
            if path.stat().st_mtime >= cutoff:
                continue
            path.unlink()
            removed += 1
        except OSError:
            continue
    return removed


def _ensure_blocked_accounts_file() -> None:
    if not BLOCKED_ACCOUNTS_FILE.exists():
        _write_text_atomic(BLOCKED_ACCOUNTS_FILE, DEFAULT_BLOCKED_ACCOUNTS_CONTENT)


def load_blocked_account_names() -> set[str]:
    ensure_runtime_dirs()
    try:
        _ensure_blocked_accounts_file()
        data = cast(list[str], _read_json_file_or_recover(BLOCKED_ACCOUNTS_FILE, "[]\n"))
    except (OSError, json.JSONDecodeError, TypeError):
        return set()
    if not isinstance(data, list):
        return set()
    return {item for item in data if isinstance(item, str) and item.strip()}


def save_blocked_account_names(names: set[str]) -> None:
    ensure_runtime_dirs()
    sorted_names = sorted(name for name in names if name.strip())
    _write_text_atomic(
        BLOCKED_ACCOUNTS_FILE,
        json.dumps(sorted_names, ensure_ascii=False, indent=2) + "\n",
    )
