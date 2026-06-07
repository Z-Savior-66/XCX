from __future__ import annotations

import json
import os
import stat
import tempfile
import time
from pathlib import Path
from typing import Any

ATOMIC_WRITE_REPLACE_ATTEMPTS = 5
ATOMIC_WRITE_RETRY_DELAY_SECONDS = 0.1


def read_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _backup_corrupt_json_file(path: Path) -> Path:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    backup_path = path.with_name(f"{path.name}.{timestamp}.{time.time_ns()}.corrupt")
    path.replace(backup_path)
    return backup_path


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


def _read_json_file_or_recover(path: Path, default_content: str) -> Any:
    try:
        return read_json_file(path)
    except json.JSONDecodeError:
        _backup_corrupt_json_file(path)
        _write_text_atomic(path, default_content)
        return json.loads(default_content)
