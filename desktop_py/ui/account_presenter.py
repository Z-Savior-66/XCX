from __future__ import annotations

from datetime import datetime

from desktop_py.core.account_state_service import (
    apply_batch_fetch_results as apply_batch_fetch_results_service,
)
from desktop_py.core.account_state_service import (
    apply_fetch_result as apply_fetch_result_service,
)
from desktop_py.core.account_status import (
    FETCH_STATUS_FAILURE,
    FETCH_STATUS_SUCCESS,
)
from desktop_py.core.account_status import (
    display_result_text as display_result_text_from_status,
)
from desktop_py.core.account_status import (
    is_expected_empty_result_note as is_expected_empty_result_note_from_core,
)
from desktop_py.core.models import AccountConfig, FetchResult
from desktop_py.core.schedule_state_service import (
    next_auto_fetch_push_interval_ms as next_auto_fetch_push_interval_ms_service,
)


def next_auto_fetch_push_interval_ms(now: datetime | None = None) -> int:
    return next_auto_fetch_push_interval_ms_service(now)


def apply_fetch_result(account: AccountConfig, result: FetchResult) -> str:
    return apply_fetch_result_service(account, result)


def apply_batch_fetch_results(accounts: list[AccountConfig], results: list[FetchResult]) -> str:
    return apply_batch_fetch_results_service(accounts, results)


def is_no_business_page_note(note: str) -> bool:
    return "页面未出现业务 iframe" in note


def is_expected_empty_result_note(note: str) -> bool:
    return is_expected_empty_result_note_from_core(note)


def transaction_complaint_pending_text(note: str) -> str:
    for segment in str(note or "").split("；"):
        value = segment.strip()
        if not value.startswith("交易投诉待处理"):
            continue
        prefix, _separator, _order_ids = value.partition("：")
        return prefix.replace("交易投诉", "", 1).strip()
    return ""


def display_deadline_text(account: AccountConfig) -> str:
    if account.is_entry_account and not account.last_deadline:
        return "--"
    if is_no_business_page_note(account.last_note):
        return "无页面"
    transaction_complaint_text = transaction_complaint_pending_text(account.last_note)
    if transaction_complaint_text:
        return transaction_complaint_text
    if account.last_status == FETCH_STATUS_SUCCESS and is_expected_empty_result_note_from_core(account.last_note):
        if "截止时间内无待处理" in account.last_note:
            return "截止时间内无待处理"
        return account.last_deadline or "无待处理"
    if account.last_status == FETCH_STATUS_SUCCESS:
        return account.last_deadline or "无待处理"
    if account.last_status == FETCH_STATUS_FAILURE:
        return account.last_note or "抓取失败"
    return account.last_deadline


def deadline_tooltip_text(account: AccountConfig) -> str:
    if account.last_status == "抓取失败" and account.last_note:
        return account.last_note
    return display_deadline_text(account)


def display_result_text(account: AccountConfig) -> str:
    return display_result_text_from_status(account.last_status)


def parse_deadline_for_sort(deadline_text: str) -> datetime | None:
    value = deadline_text.strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def sort_accounts_for_display(accounts: list[AccountConfig]) -> list[AccountConfig]:
    indexed_accounts = list(enumerate(accounts))

    def sort_key(item: tuple[int, AccountConfig]) -> tuple[int, int, datetime, int]:
        index, account = item
        if account.is_entry_account:
            return (0, 0, datetime.min, index)
        deadline = parse_deadline_for_sort(account.last_deadline)
        if deadline is not None:
            return (1, 0, deadline, index)
        return (2, 0, datetime.max, index)

    return [account for _, account in sorted(indexed_accounts, key=sort_key)]


def display_account_name(account: AccountConfig, current_main_account_name: str) -> str:
    if account.is_entry_account:
        current_name = current_main_account_name.strip()
        if current_name:
            return f"主账号状态：{current_name}"
        return "主账号状态：未记录"
    return account.name
