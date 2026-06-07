from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from desktop_py.core.fetcher_common import _safe_int
from desktop_py.core.file_io import read_json_file


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value or default)
    except TypeError, ValueError:
        return default


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


RUNNING_INSTANCE_LOCK_STALE_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class AppInstanceLock:
    path: Path
    pid: int
    token: str

    def release(self) -> None:
        try:
            payload = read_json_file(self.path)
        except OSError, json.JSONDecodeError:
            return
        if not isinstance(payload, dict):
            return
        if _safe_int(payload.get("pid", 0)) != self.pid or str(payload.get("token", "") or "") != self.token:
            return
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass


def acquire_app_instance_lock(
    *,
    lock_path: Path,
    stale_seconds: int = RUNNING_INSTANCE_LOCK_STALE_SECONDS,
    process_id_fn: Callable[[], int] = os.getpid,
    process_running_fn: Callable[[int], bool] = _process_is_running,
    now_fn: Callable[[], float] = time.time,
    ensure_dirs_fn: Callable[[], None] | None = None,
) -> AppInstanceLock:
    if ensure_dirs_fn is not None:
        ensure_dirs_fn()
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
            except OSError, json.JSONDecodeError:
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
