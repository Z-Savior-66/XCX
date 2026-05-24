from __future__ import annotations

from desktop_py.core.account_status import fetch_status_from_result
from desktop_py.core.models import SESSION_STATUS_VALID, AccountConfig, FetchResult


def apply_fetch_result(account: AccountConfig, result: FetchResult) -> str:
    account.last_fetch_at = result.fetched_at
    account.last_deadline = result.deadline_text
    account.last_status = fetch_status_from_result(result.ok, result.note)
    actual_note = f"当前实际账号：{result.actual_account_name}" if result.actual_account_name else ""
    account.last_note = "；".join(item for item in [result.note, actual_note] if item)
    account.feedback_url = result.page_url
    account.last_actual_account_name = result.actual_account_name or account.last_actual_account_name
    account.last_session_verified_at = result.fetched_at
    if result.ok:
        account.session_status = SESSION_STATUS_VALID
        account.last_session_error = ""
    return result.actual_account_name or account.name


def apply_batch_fetch_results(accounts: list[AccountConfig], results: list[FetchResult]) -> str:
    latest_actual_account_name = ""
    result_map = {result.account_name: result for result in results}
    for account in accounts:
        result = result_map.get(account.name)
        if result is None:
            continue
        account.last_fetch_at = result.fetched_at
        account.last_deadline = result.deadline_text
        account.last_status = fetch_status_from_result(result.ok, result.note)
        actual_note = f"当前实际账号：{result.actual_account_name}" if result.actual_account_name else ""
        account.last_note = "；".join(item for item in [result.note, actual_note] if item)
        if result.page_url:
            account.feedback_url = result.page_url
        if result.actual_account_name:
            account.last_actual_account_name = result.actual_account_name
        account.last_session_verified_at = result.fetched_at
        if result.ok:
            account.session_status = SESSION_STATUS_VALID
            account.last_session_error = ""
        if result.actual_account_name:
            latest_actual_account_name = result.actual_account_name
    return latest_actual_account_name
