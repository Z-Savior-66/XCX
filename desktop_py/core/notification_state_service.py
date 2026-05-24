from __future__ import annotations

from desktop_py.core.models import AccountConfig


def clear_pushed_fetch_state(accounts: list[AccountConfig]) -> int:
    cleared = 0
    for account in accounts:
        if account.is_entry_account or not account.enabled:
            continue
        if account.last_status != "抓取成功":
            continue
        account.last_deadline = ""
        account.last_status = ""
        account.last_note = ""
        cleared += 1
    return cleared


def actual_account_name_from_note(note: str, *, actual_account_prefix: str) -> str:
    for part in note.split("；"):
        text = part.strip()
        if text.startswith(actual_account_prefix):
            return text.removeprefix(actual_account_prefix).strip()
    return ""
