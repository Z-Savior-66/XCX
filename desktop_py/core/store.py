from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, cast

from desktop_py.core.fetcher_common import _safe_int
from desktop_py.core.models import AccountConfig, AppSettings, FetchResult, ScheduleState

APP_NAME = "小程序工具"
SHARED_BROWSER_PROFILE_DIR_NAME = "browser_profile"
BROWSER_PROFILE_LOCK_FILES = (
    "SingletonLock",
    "SingletonCookie",
    "SingletonSocket",
    "LOCK",
    "lockfile",
)
ATOMIC_WRITE_REPLACE_ATTEMPTS = 5
ATOMIC_WRITE_RETRY_DELAY_SECONDS = 0.1
RUNNING_INSTANCE_LOCK_STALE_SECONDS = 24 * 60 * 60


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


@dataclass(frozen=True)
class AppInstanceLock:
    path: Path
    pid: int
    token: str

    def release(self) -> None:
        try:
            payload = read_json_file(self.path)
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        if _safe_int(payload.get("pid", 0)) != self.pid or str(payload.get("token", "") or "") != self.token:
            return
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass


def read_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


def _backup_corrupt_json_file(path: Path) -> Path:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    backup_path = path.with_name(f"{path.name}.{timestamp}.{time.time_ns()}.corrupt")
    path.replace(backup_path)
    return backup_path


def _read_json_file_or_recover(path: Path, default_content: str) -> Any:
    try:
        return read_json_file(path)
    except json.JSONDecodeError:
        _backup_corrupt_json_file(path)
        _write_text_atomic(path, default_content)
        return json.loads(default_content)


def _process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _lock_payload_is_active(
    payload: object,
    *,
    now: float,
    stale_seconds: int,
    process_running_fn: Callable[[int], bool],
) -> bool:
    if not isinstance(payload, dict):
        return False
    pid = _safe_int(payload.get("pid", 0))
    if pid <= 0:
        return False
    if process_running_fn(pid):
        return True
    created_at = _safe_float(payload.get("created_at", 0))
    if created_at <= 0:
        return False
    if now - created_at >= stale_seconds:
        return False
    return False


def acquire_app_instance_lock(
    *,
    lock_path: Path = RUNNING_INSTANCE_LOCK_FILE,
    stale_seconds: int = RUNNING_INSTANCE_LOCK_STALE_SECONDS,
    process_id_fn: Callable[[], int] = os.getpid,
    process_running_fn: Callable[[int], bool] = _process_is_running,
    now_fn: Callable[[], float] = time.time,
) -> AppInstanceLock:
    ensure_runtime_dirs()
    token = str(time.time_ns())
    pid = process_id_fn()
    payload = {"pid": pid, "token": token, "created_at": now_fn()}
    content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    for _attempt in range(2):
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                existing_payload = read_json_file(lock_path)
            except (OSError, json.JSONDecodeError):
                existing_payload = {}
            if _lock_payload_is_active(
                existing_payload,
                now=now_fn(),
                stale_seconds=stale_seconds,
                process_running_fn=process_running_fn,
            ):
                raise RuntimeError("小程序工具已在运行，请先关闭现有窗口或托盘图标后再启动。") from None
            try:
                lock_path.unlink(missing_ok=True)
            except OSError as exc:
                raise RuntimeError(f"清理旧运行锁失败，请关闭现有程序后重试：{exc}") from exc
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as lock_file:
            lock_file.write(content)
        return AppInstanceLock(lock_path, pid, token)
    raise RuntimeError("小程序工具已在运行，请先关闭现有窗口或托盘图标后再启动。")


def _write_text_atomic(path: Path, content: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if path.exists() and path.read_text(encoding=encoding) == content:
            return
    except FileNotFoundError:
        pass
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding=encoding,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = temp_file.name
            temp_file.write(content)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        for attempt in range(ATOMIC_WRITE_REPLACE_ATTEMPTS):
            try:
                Path(temp_path).replace(path)
                break
            except PermissionError:
                if attempt == ATOMIC_WRITE_REPLACE_ATTEMPTS - 1:
                    raise
                time.sleep(ATOMIC_WRITE_RETRY_DELAY_SECONDS)
        try:
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
    except Exception:
        if temp_path:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                pass
        raise


def validate_shared_browser_profile_dir(profile_dir: str) -> str:
    value = profile_dir.strip()
    if not value:
        return ""

    path = Path(value).expanduser()
    if not path.exists():
        raise ValueError("共享浏览器资料目录不存在，请选择已存在的目录。")
    if not path.is_dir():
        raise ValueError("共享浏览器资料目录必须是文件夹。")

    resolved = path.resolve()
    if _looks_like_default_browser_profile_dir(resolved):
        raise ValueError("共享浏览器资料目录不能直接指向 Chrome 或 Edge 的默认用户资料目录，请改用专用自动化目录。")
    if _has_browser_lock_markers(resolved):
        raise ValueError("共享浏览器资料目录当前疑似正被浏览器占用，请先关闭相关浏览器后再使用。")
    return str(resolved)


def prepare_shared_browser_profile_dir(parent_dir: str) -> str:
    value = parent_dir.strip()
    if not value:
        return ""

    parent = Path(value).expanduser()
    if parent.exists() and not parent.is_dir():
        raise ValueError("共享浏览器资料父目录必须是文件夹。")

    target = parent if parent.name == SHARED_BROWSER_PROFILE_DIR_NAME else parent / SHARED_BROWSER_PROFILE_DIR_NAME
    target.mkdir(parents=True, exist_ok=True)
    return validate_shared_browser_profile_dir(str(target))


def _looks_like_default_browser_profile_dir(path: Path) -> bool:
    name = path.name.lower()
    parent_name = path.parent.name.lower()
    if name == "user data" and (path / "Local State").exists():
        return True
    if parent_name == "user data" and (path / "Preferences").exists():
        return True
    return False


def _has_browser_lock_markers(path: Path) -> bool:
    if any((path / lock_name).exists() for lock_name in BROWSER_PROFILE_LOCK_FILES):
        return True
    parent = path.parent
    if parent.name.lower() == "user data":
        return any((parent / lock_name).exists() for lock_name in BROWSER_PROFILE_LOCK_FILES)
    return False


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
