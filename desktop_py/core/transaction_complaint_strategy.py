from __future__ import annotations

from collections.abc import Callable
from math import ceil
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from desktop_py.core.fetcher_common import CancelCheck, Logger, _wait_for_timeout
from desktop_py.core.fetcher_rules import (
    DEFAULT_TRANSACTION_COMPLAINT_RULES,
    TransactionComplaintRuleSet,
    load_transaction_complaint_rules,
)
from desktop_py.core.fetcher_support import (
    FetchError,
    FetchErrorCode,
    fetch_error_code,
    is_login_timeout_page,
    recover_login_timeout_page,
)
from desktop_py.core.models import AccountConfig
from desktop_py.core.parser import convert_timestamp
from desktop_py.core.response_capture import extract_response_token
from desktop_py.core.store import write_account_output_json, write_account_output_text

PENDING_TRANSACTION_COMPLAINT_STATUS = DEFAULT_TRANSACTION_COMPLAINT_RULES.pending_status
TRANSACTION_COMPLAINT_PAGE_SIZE = DEFAULT_TRANSACTION_COMPLAINT_RULES.page_size
TRANSACTION_COMPLAINT_STATUS_TEXT = {
    DEFAULT_TRANSACTION_COMPLAINT_RULES.pending_status: DEFAULT_TRANSACTION_COMPLAINT_RULES.pending_status_text
}

LogFn = Callable[[Logger | None, str], None]


def _resolve_transaction_complaint_rules(
    rules: TransactionComplaintRuleSet | None = None,
) -> TransactionComplaintRuleSet:
    return rules if rules is not None else load_transaction_complaint_rules()


def should_fetch_transaction_complaints(
    account: AccountConfig, rules: TransactionComplaintRuleSet | None = None
) -> bool:
    resolved_rules = _resolve_transaction_complaint_rules(rules)
    return account.name.strip() in resolved_rules.target_account_names


def build_transaction_complaint_page_url(token: str) -> str:
    query = urlencode({"token": token, "lang": "zh_CN"})
    return f"https://mp.weixin.qq.com/wxamp/deal/complaint?{query}"


def build_transaction_complaint_list_url(
    token: str,
    *,
    page: int,
    page_size: int | None = None,
    status: int | None = None,
    rules: TransactionComplaintRuleSet | None = None,
) -> str:
    resolved_rules = _resolve_transaction_complaint_rules(rules)
    resolved_page_size = page_size if page_size is not None else resolved_rules.page_size
    resolved_status = status if status is not None else resolved_rules.pending_status
    query = urlencode(
        {
            "token": token,
            "lang": "zh_CN",
            "page": page,
            "pageSize": resolved_page_size,
            "status": resolved_status,
            "sortType": 2,
            "type": "",
            "phoneNumber": "",
            "complaintOrderId": "",
        }
    )
    return f"https://mp.weixin.qq.com/wxamp/xframe/guarant/cgi/complaint/getComplaintOrderList?{query}"


def request_transaction_complaint_json(page: Any, request_url: str) -> dict[str, Any]:
    payload = page.evaluate(
        """async (url) => {
            const response = await fetch(url, { credentials: 'include' });
            const text = await response.text();
            try {
                return JSON.parse(text);
            } catch {
                return { ret: -1, errmsg: text };
            }
        }""",
        request_url,
    )
    if not isinstance(payload, dict):
        raise FetchError(
            "交易投诉接口返回格式异常。",
            code=FetchErrorCode.TRANSACTION_COMPLAINT_RESPONSE_INVALID,
            evidence=[
                {
                    "kind": "network",
                    "label": "交易投诉接口响应",
                    "summary": "接口响应无法解析为 JSON 对象。",
                    "metadata": {"request_url": request_url, "payload_type": type(payload).__name__},
                }
            ],
        )
    return payload


def open_transaction_complaint_page(
    page: Any,
    *,
    account: AccountConfig,
    logger: Logger | None,
    log_fn: LogFn,
    wait_for_url_contains_fn: Callable[..., Any],
    safe_page_content_fn: Callable[..., str],
    is_cancelled: CancelCheck | None = None,
) -> str:
    token = extract_response_token(str(getattr(page, "url", "") or ""))
    if not token:
        page.goto(account.home_url, wait_until="domcontentloaded", timeout=60000)
        wait_for_url_contains_fn(page, ("token=", "/wxamp/index/index"), timeout_ms=4000, is_cancelled=is_cancelled)
        token = extract_response_token(str(getattr(page, "url", "") or ""))
    if not token:
        raise FetchError(
            "交易投诉采集失败：当前页面缺少后台 token。",
            code=FetchErrorCode.MISSING_TOKEN,
            evidence=[
                {
                    "kind": "page",
                    "label": "当前页面地址",
                    "summary": "交易投诉采集入口未找到后台 token。",
                    "metadata": {"page_url": str(getattr(page, "url", "") or "")},
                }
            ],
        )

    complaint_url = build_transaction_complaint_page_url(token)
    page.goto(complaint_url, wait_until="domcontentloaded", timeout=60000)
    wait_for_url_contains_fn(page, ("/wxamp/deal/complaint", "/wxamp/deal"), timeout_ms=5000, is_cancelled=is_cancelled)
    if is_login_timeout_page(page, safe_page_content_fn=safe_page_content_fn):
        recover_login_timeout_page(
            page,
            logger=logger,
            log_fn=log_fn,
            safe_page_content_fn=safe_page_content_fn,
            wait_or_cancel_fn=_wait_for_timeout,
            is_cancelled=is_cancelled,
        )
    try:
        page.wait_for_load_state("networkidle", timeout=6000)
    except Exception:
        pass
    return str(getattr(page, "url", "") or complaint_url)


def normalize_transaction_complaint_item(
    item: dict[str, Any], rules: TransactionComplaintRuleSet | None = None
) -> dict[str, Any]:
    resolved_rules = _resolve_transaction_complaint_rules(rules)
    raw_status = item.get("status", 0)
    try:
        status = int(raw_status)
    except (TypeError, ValueError):
        status = 0
    return {
        "complaint_order_id": str(item.get("complaintOrderId", "") or "").strip(),
        "status": status,
        "status_text": resolved_rules.pending_status_text
        if status == resolved_rules.pending_status
        else str(raw_status).strip(),
        "type": item.get("type", ""),
        "order_id": str(item.get("orderId", "") or "").strip(),
        "out_trade_no": str(item.get("outTradeNo", "") or "").strip(),
        "phone_number": str(item.get("phoneNumber", "") or "").strip(),
        "nick_name": str(item.get("nickName", "") or "").strip(),
        "create_time": convert_timestamp(str(item.get("createTime", "") or "").strip()),
        "expire_time": convert_timestamp(str(item.get("expireTime", "") or "").strip()),
        "product_name": str(item.get("productName", "") or "").strip(),
        "total_cost": item.get("totalCost", ""),
    }


def fetch_pending_transaction_complaint_items(
    page: Any,
    token: str,
    *,
    request_json_fn: Callable[[Any, str], dict[str, Any]] = request_transaction_complaint_json,
    rules: TransactionComplaintRuleSet | None = None,
) -> list[dict[str, Any]]:
    resolved_rules = _resolve_transaction_complaint_rules(rules)
    first_url = build_transaction_complaint_list_url(token, page=1, rules=resolved_rules)
    first_payload = request_json_fn(page, first_url)
    if int(first_payload.get("ret", 0) or 0) != 0:
        raise FetchError(
            f"交易投诉接口返回失败：{first_payload.get('errmsg', '未知错误')}",
            code=FetchErrorCode.TRANSACTION_COMPLAINT_API_FAILED,
            evidence=[
                {
                    "kind": "network",
                    "label": "交易投诉列表接口",
                    "summary": "交易投诉列表接口 ret 非 0。",
                    "metadata": {"request_url": first_url, "ret": first_payload.get("ret")},
                }
            ],
        )

    total = int(first_payload.get("countAll", 0) or 0)
    raw_items = first_payload.get("complaintOrderList", [])
    items = [item for item in raw_items if isinstance(item, dict)]
    total_pages = max(1, ceil(total / resolved_rules.page_size))

    for page_index in range(2, total_pages + 1):
        payload = request_json_fn(
            page,
            build_transaction_complaint_list_url(token, page=page_index, rules=resolved_rules),
        )
        if int(payload.get("ret", 0) or 0) != 0:
            raise FetchError(
                f"交易投诉分页接口返回失败：{payload.get('errmsg', '未知错误')}",
                code=FetchErrorCode.TRANSACTION_COMPLAINT_API_FAILED,
                evidence=[
                    {
                        "kind": "network",
                        "label": "交易投诉分页接口",
                        "summary": "交易投诉分页接口 ret 非 0。",
                        "metadata": {"page": page_index, "ret": payload.get("ret")},
                    }
                ],
            )
        page_items = payload.get("complaintOrderList", [])
        items.extend(item for item in page_items if isinstance(item, dict))

    return [
        normalize_transaction_complaint_item(item, rules=resolved_rules)
        for item in items
        if int(item.get("status", 0) or 0) == resolved_rules.pending_status
    ]


def build_transaction_complaint_summary(complaints: list[dict[str, Any]]) -> str:
    if not complaints:
        return "交易投诉无待处理投诉。"
    order_ids = "、".join(str(item["complaint_order_id"]) for item in complaints[:3] if item.get("complaint_order_id"))
    suffix = " 等" if len(complaints) > 3 else ""
    return f"交易投诉待处理 {len(complaints)} 条：{order_ids}{suffix}"


def fetch_transaction_complaints(
    page: Any,
    *,
    account: AccountConfig,
    logger: Logger | None,
    output_dir: Path,
    log_fn: LogFn,
    wait_for_url_contains_fn: Callable[..., Any],
    safe_page_content_fn: Callable[..., str],
    is_cancelled: CancelCheck | None = None,
    request_json_fn: Callable[[Any, str], dict[str, Any]] = request_transaction_complaint_json,
    rules: TransactionComplaintRuleSet | None = None,
) -> dict[str, Any]:
    resolved_rules = _resolve_transaction_complaint_rules(rules)
    if not should_fetch_transaction_complaints(account, resolved_rules):
        return {
            "ok": True,
            "enabled": False,
            "complaints": [],
            "summary": "",
            "page_url": str(getattr(page, "url", "") or ""),
        }

    try:
        page_url = open_transaction_complaint_page(
            page,
            account=account,
            logger=logger,
            log_fn=log_fn,
            wait_for_url_contains_fn=wait_for_url_contains_fn,
            safe_page_content_fn=safe_page_content_fn,
            is_cancelled=is_cancelled,
        )
        token = extract_response_token(page_url)
        complaints = fetch_pending_transaction_complaint_items(
            page, token, request_json_fn=request_json_fn, rules=resolved_rules
        )
        write_account_output_json(account.name, "transaction_complaints.json", complaints)
        summary = build_transaction_complaint_summary(complaints)
        return {"ok": True, "enabled": True, "complaints": complaints, "summary": summary, "page_url": page_url}
    except Exception as exc:
        try:
            write_account_output_text(account.name, "transaction_complaint_page.html", safe_page_content_fn(page))
        except Exception:
            pass
        write_account_output_json(account.name, "transaction_complaints.json", [])
        message = f"交易投诉抓取失败：{exc}"
        log_fn(logger, f"账号 {account.name} {message}")
        return {
            "ok": False,
            "enabled": True,
            "complaints": [],
            "summary": message,
            "page_url": str(getattr(page, "url", "") or ""),
            "error_code": fetch_error_code(exc),
        }
