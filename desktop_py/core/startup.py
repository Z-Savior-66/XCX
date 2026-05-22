from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from desktop_py.core.store import APP_NAME

RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


class StartupUnavailableError(RuntimeError):
    pass


def startup_command(
    *,
    executable_path: Path | None = None,
    script_path: Path | None = None,
    frozen: bool | None = None,
    os_name: str | None = None,
) -> str:
    current_os_name = os.name if os_name is None else os_name
    if current_os_name != "nt":
        raise StartupUnavailableError("开机自启仅支持 Windows。")

    current_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    executable = executable_path or Path(sys.executable)
    if current_frozen:
        return subprocess.list2cmdline([str(executable)])

    pythonw = executable.with_name("pythonw.exe")
    launcher = pythonw if pythonw.exists() else executable
    target = script_path or Path(__file__).resolve().parents[2] / "desktop_main.py"
    return subprocess.list2cmdline([str(launcher), str(target)])


def _winreg_module() -> Any:
    if os.name != "nt":
        raise StartupUnavailableError("开机自启仅支持 Windows。")
    import winreg

    return winreg


def get_startup_enabled(
    *,
    value_name: str = APP_NAME,
    registry: Any | None = None,
    os_name: str | None = None,
) -> bool:
    current_os_name = os.name if os_name is None else os_name
    if current_os_name != "nt":
        return False

    registry_api = registry or _winreg_module()
    try:
        key = registry_api.OpenKey(registry_api.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, registry_api.KEY_READ)
    except OSError:
        return False
    try:
        value, _value_type = registry_api.QueryValueEx(key, value_name)
    except OSError:
        return False
    finally:
        registry_api.CloseKey(key)
    return bool(str(value).strip())


def set_startup_enabled(
    enabled: bool,
    *,
    value_name: str = APP_NAME,
    command: str | None = None,
    registry: Any | None = None,
    os_name: str | None = None,
) -> None:
    current_os_name = os.name if os_name is None else os_name
    if current_os_name != "nt":
        raise StartupUnavailableError("开机自启仅支持 Windows。")

    registry_api = registry or _winreg_module()
    if enabled:
        startup_value = command or startup_command(os_name=current_os_name)
        key = registry_api.CreateKeyEx(registry_api.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, registry_api.KEY_SET_VALUE)
        try:
            registry_api.SetValueEx(key, value_name, 0, registry_api.REG_SZ, startup_value)
        finally:
            registry_api.CloseKey(key)
        return

    try:
        key = registry_api.OpenKey(registry_api.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, registry_api.KEY_SET_VALUE)
    except OSError:
        return
    try:
        registry_api.DeleteValue(key, value_name)
    except OSError:
        return
    finally:
        registry_api.CloseKey(key)
