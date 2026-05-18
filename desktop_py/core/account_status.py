from __future__ import annotations

from typing import Final

FETCH_STATUS_SUCCESS: Final[str] = "抓取成功"
FETCH_STATUS_FAILURE: Final[str] = "抓取失败"
LOGIN_STATUS_VALID: Final[str] = "登录有效"
LOGIN_STATUS_INVALID: Final[str] = "登录失效"
LOGIN_STATUS_SAVED: Final[str] = "已保存登录态"
STATUS_CHECKING: Final[str] = "检测中"
RESULT_STATUS_DONE: Final[str] = "完成"
RESULT_STATUS_FAILED: Final[str] = "失败"
RESULT_STATUS_EMPTY: Final[str] = ""

SUCCESS_ACCOUNT_STATUSES: Final[frozenset[str]] = frozenset(
    {FETCH_STATUS_SUCCESS, LOGIN_STATUS_VALID, LOGIN_STATUS_SAVED}
)
EXPECTED_EMPTY_RESULT_NOTES: Final[frozenset[str]] = frozenset({"当前账号无待处理申请"})
NO_BUSINESS_PAGE_NOTE: Final[str] = "页面未出现业务 iframe"
AUTO_PUSH_SKIP_NOTE: Final[str] = "当前登录态未自动跳入后台页，且没有可复用的历史反馈页地址，无法启动自动切换账号。"


def is_expected_empty_result_note(note: str) -> bool:
    value = note.strip()
    return bool(value) and (
        NO_BUSINESS_PAGE_NOTE in value or any(item in value for item in EXPECTED_EMPTY_RESULT_NOTES)
    )


def fetch_status_from_result(ok: bool, note: str) -> str:
    if ok or is_expected_empty_result_note(note):
        return FETCH_STATUS_SUCCESS
    return FETCH_STATUS_FAILURE


def display_result_text(last_status: str) -> str:
    value = last_status.strip()
    if value in SUCCESS_ACCOUNT_STATUSES:
        return RESULT_STATUS_DONE
    if not value or value == STATUS_CHECKING:
        return RESULT_STATUS_EMPTY
    return RESULT_STATUS_FAILED
