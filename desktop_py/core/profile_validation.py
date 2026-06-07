from __future__ import annotations

from pathlib import Path

SHARED_BROWSER_PROFILE_DIR_NAME = "browser_profile"
BROWSER_PROFILE_LOCK_FILES = (
    "SingletonLock",
    "SingletonCookie",
    "SingletonSocket",
    "LOCK",
    "lockfile",
)


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
