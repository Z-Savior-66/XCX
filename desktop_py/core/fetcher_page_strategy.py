from __future__ import annotations

import re
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from desktop_py.core.fetcher_common import CancelCheck, Logger, _log
from desktop_py.core.fetcher_output import persist_storage_state
from desktop_py.core.fetcher_rules import DEFAULT_REFUND_RULES
from desktop_py.core.fetcher_support import FetchError, FetchErrorCode, _fallback_from_responses
from desktop_py.core.models import AccountConfig, FetchResult
from desktop_py.core.response_capture import (
    _capture_response_payload,
    classify_refund_response_type,
    extract_response_token,
)
from desktop_py.core.store import write_account_output_text, write_fetch_result

LogFn = Callable[[Logger | None, str], None]

REFUND_COUNT_PATTERN = re.compile(r"退款申请[（(]\s*(\d+)\s*[）)]")
DEADLINE_DATETIME_PATTERN = re.compile(r"处理截止时间[：:\s]{0,8}\d{4}[-年]\d{1,2}[-月]\d{1,2}")
DEADLINE_TIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d")


def register_response_capture(
    page: Any, capture_response_payload_fn: Callable[..., Any]
) -> tuple[list[Any], Callable[[], None]]:
    captures: list[Any] = []

    def handle_response(response: Any) -> None:
        capture = capture_response_payload_fn(response)
        if capture is not None:
            captures.append(capture)

    page.on("response", handle_response)

    def cleanup() -> None:
        try:
            page.remove_listener("response", handle_response)
        except Exception:
            pass

    return captures, cleanup


def filter_detail_captures(captures: list[Any], feedback_url: str) -> list[Any]:
    current_token = (parse_qs(urlparse(feedback_url).query).get("token") or [""])[0].strip()
    if not captures:
        return []

    filtered: list[Any] = []
    for capture in captures:
        if not isinstance(capture, dict):
            continue
        capture_url = str(capture.get("url", "") or "").strip()
        if not capture_url:
            continue
        response_type = str(capture.get("response_type", "") or "").strip()
        capture_token = str(capture.get("token", "") or "").strip()
        if current_token and capture_token and capture_token != current_token:
            continue
        if response_type in {"detail", "list"}:
            filtered.append(capture)
            continue
        if any(keyword in capture_url for keyword in ("gameFeedback", "refund")):
            if current_token and capture_token and capture_token != current_token:
                continue
            filtered.append(capture)
    return filtered


def _latest_refund_capture(captures: list[Any], response_type: str) -> dict[str, Any] | None:
    for capture in reversed(captures):
        if not isinstance(capture, dict):
            continue
        if str(capture.get("response_type", "") or "").strip() != response_type:
            continue
        return capture
    return None


def _refund_list_captures(captures: list[Any]) -> list[dict[str, Any]]:
    return [capture for capture in captures if isinstance(capture, dict) and capture.get("response_type") == "list"]


def _refund_items_from_capture(capture: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not capture:
        return []
    body = capture.get("body")
    if not isinstance(body, dict):
        return []
    data = body.get("data")
    if not isinstance(data, dict):
        return []
    items = data.get("user_refund_check_list")
    if not isinstance(items, list):
        items = data.get("list")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _parse_deadline_text(value: str) -> datetime | None:
    text = str(value).strip()
    if not text:
        return None
    for fmt in DEADLINE_TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _earliest_deadline_text(deadlines: list[str]) -> str:
    dated = [(parsed, text.strip()) for text in deadlines if (parsed := _parse_deadline_text(text)) is not None]
    if not dated:
        return ""
    return min(dated, key=lambda item: item[0])[1]


def _refund_list_capture_pagination(capture: dict[str, Any] | None) -> tuple[str, int, int, int, int]:
    if not capture:
        return "", 0, 0, 0, 0
    capture_url = str(capture.get("url", "") or "").strip()
    if not capture_url:
        return "", 0, 0, 0, 0
    body = capture.get("body")
    if not isinstance(body, dict):
        return "", 0, 0, 0, 0
    data = body.get("data")
    if not isinstance(data, dict):
        return "", 0, 0, 0, 0
    total_count = int(data.get("total_count") or data.get("total_cnt") or 0)
    item_count = len(_refund_items_from_capture(capture))
    query = parse_qs(urlparse(capture_url).query)
    per_page = int((query.get("per_page") or ["0"])[0] or 0)
    current_page = int((query.get("cur_page") or ["0"])[0] or 0)
    return capture_url, current_page, per_page, total_count, item_count


def request_refund_list_page(page: Any, request_url: str) -> Any:
    return page.evaluate(
        """async (url) => {
            const response = await fetch(url, { credentials: 'include' });
            const text = await response.text();
            try {
                return JSON.parse(text);
            } catch {
                return text;
            }
        }""",
        request_url,
    )


def fetch_paginated_refund_list_captures(
    *,
    page: Any,
    captures: list[Any],
    logger: Logger | None,
    log_fn: LogFn,
    request_refund_list_page_fn: Callable[[Any, str], Any],
) -> list[Any]:
    list_captures = _refund_list_captures(captures)
    latest_list_capture = list_captures[-1] if list_captures else None
    capture_url, _current_page, per_page, total_count, item_count = _refund_list_capture_pagination(latest_list_capture)
    if not capture_url or per_page <= 0 or total_count <= max(item_count, per_page):
        return captures

    parsed_url = urlparse(capture_url)
    base_query = parse_qs(parsed_url.query)
    total_pages = (total_count + per_page - 1) // per_page
    seen_pages: set[int] = set()
    for capture in list_captures:
        _, current_page, _, _, _ = _refund_list_capture_pagination(capture)
        seen_pages.add(current_page)

    extended_captures = list(captures)
    for page_index in range(total_pages):
        if page_index in seen_pages:
            continue
        query = {key: list(value) for key, value in base_query.items()}
        query["cur_page"] = [str(page_index)]
        page_url = urlunparse(parsed_url._replace(query=urlencode(query, doseq=True)))
        body = request_refund_list_page_fn(page, page_url)
        extended_captures.append(
            {
                "url": page_url,
                "status": 200,
                "content_type": "application/json",
                "body": body,
                "token": str((query.get("token") or [""])[0]).strip(),
                "response_type": "list",
                "captured_at": time.time(),
            }
        )
        log_fn(logger, f"退款列表分页补抓成功：第 {page_index + 1}/{total_pages} 页。")
    return extended_captures


def list_capture_result(captures: list[Any]) -> str:
    capture = _latest_refund_capture(captures, "list")
    if capture is None:
        return "unknown"
    body = capture.get("body")
    if not isinstance(body, dict):
        return "unknown"
    data = body.get("data")
    if not isinstance(data, dict):
        return "unknown"
    raw_items = data.get("user_refund_check_list")
    if not isinstance(raw_items, list):
        raw_items = data.get("list")
    if isinstance(raw_items, list):
        items = [item for item in raw_items if isinstance(item, dict)]
        if items:
            return "non_empty"
        return "empty"
    total_count = data.get("total_count")
    if total_count is None:
        total_count = data.get("total_cnt")
    if total_count == 0 or str(total_count).strip() == "0":
        return "empty"
    return "unknown"


def extract_deadline_from_refund_capture(capture: dict[str, Any] | None) -> str:
    candidates: list[str] = []
    items = _refund_items_from_capture(capture)
    for item in items:
        deadline_text = _fallback_from_responses([item])
        if deadline_text:
            candidates.append(deadline_text)
    if capture is None:
        return ""
    fallback_deadline = _fallback_from_responses([capture])
    if fallback_deadline:
        candidates.append(fallback_deadline)
    return _earliest_deadline_text(candidates)


def extract_deadline_from_captures(captures: list[Any]) -> str:
    detail_capture = _latest_refund_capture(captures, "detail")
    deadline_text = extract_deadline_from_refund_capture(detail_capture)
    list_captures = _refund_list_captures(captures)
    list_deadline = _earliest_deadline_text(
        [extract_deadline_from_refund_capture(capture) for capture in list_captures]
    )
    if deadline_text and list_deadline:
        return _earliest_deadline_text([deadline_text, list_deadline]) or deadline_text
    if deadline_text:
        return deadline_text
    return list_deadline


def _list_captures_for_feedback_url(captures: list[Any], feedback_url: str) -> list[dict[str, Any]]:
    current_token = (parse_qs(urlparse(feedback_url).query).get("token") or [""])[0].strip()
    current_list_captures: list[dict[str, Any]] = []
    for capture in _refund_list_captures(captures):
        capture_token = str(capture.get("token", "") or "").strip()
        if current_token and capture_token and capture_token != current_token:
            continue
        current_list_captures.append(capture)
    return current_list_captures


def matches_refund_response_contract(response: Any, feedback_url: str, response_type: str) -> bool:
    status = int(getattr(response, "status", 0) or 0)
    if status < 200 or status >= 400:
        return False
    response_url = str(getattr(response, "url", "") or "").strip()
    if not response_url:
        return False
    current_token = (parse_qs(urlparse(feedback_url).query).get("token") or [""])[0].strip()
    response_token = extract_response_token(response_url)
    if current_token and response_token and response_token != current_token:
        return False
    return classify_refund_response_type(response_url, {}) == response_type


def wait_for_action_response_contract(
    page: Any,
    *,
    action_fn: Callable[[], None],
    feedback_url: str,
    response_type: str,
    timeout_ms: int = 8000,
) -> dict[str, Any] | None:
    try:
        expect_response = page.expect_response
    except AttributeError:
        action_fn()
        return None

    try:
        with expect_response(
            lambda response: matches_refund_response_contract(response, feedback_url, response_type),
            timeout=timeout_ms,
        ) as response_info:
            action_fn()
        capture = _capture_response_payload(response_info.value)
    except Exception:
        return None
    if isinstance(capture, dict):
        return capture
    return None


def open_feedback_page(
    page: Any,
    *,
    account: AccountConfig,
    logger: Logger | None,
    build_feedback_url_fn: Callable[[str], str],
    wait_for_iframe_ready_fn: Callable[..., bool],
    is_cancelled: CancelCheck | None = None,
) -> str:
    feedback_url = build_feedback_url_fn(page.url)
    page.goto(feedback_url, wait_until="domcontentloaded", timeout=60000)
    wait_for_iframe_ready_fn(page, timeout_ms=5000, is_cancelled=is_cancelled)
    return feedback_url


def resolve_frame_locator(
    page: Any,
    *,
    output_dir: Path,
    business_iframe_selector_fn: Callable[..., str],
    safe_page_content_fn: Callable[..., str],
) -> Any:
    iframe_selector = business_iframe_selector_fn(page)
    if not iframe_selector:
        html = safe_page_content_fn(page)
        write_account_output_text(output_dir.name, "page.html", html)
        raise FetchError(
            "页面未出现业务 iframe，可能是链接失效、无权限或登录态失效。",
            code=FetchErrorCode.BUSINESS_IFRAME_MISSING,
            evidence=[
                {
                    "kind": "html",
                    "label": "页面 HTML",
                    "path": str(output_dir / "page.html"),
                    "summary": "未定位到业务 iframe，已保存当前页面 HTML。",
                    "metadata": {"page_url": str(getattr(page, "url", "") or "")},
                }
            ],
        )
    return page.frame_locator(iframe_selector)


def is_empty_refund_list(list_text: str) -> bool:
    return any(marker in list_text for marker in DEFAULT_REFUND_RULES.empty_list_markers) or any(
        int(match.group(1)) == 0 for match in REFUND_COUNT_PATTERN.finditer(list_text)
    )


def has_definite_pending_refund_signal(list_text: str) -> bool:
    if DEADLINE_DATETIME_PATTERN.search(list_text):
        return True
    return any(int(match.group(1)) > 0 for match in REFUND_COUNT_PATTERN.finditer(list_text))


def has_pending_refund_signal(list_text: str) -> bool:
    text = list_text.strip()
    if not text:
        return False
    if has_definite_pending_refund_signal(text):
        return True
    has_empty_marker = is_empty_refund_list(text)
    weak_markers = {"退款申请(", "处理"}
    for marker in DEFAULT_REFUND_RULES.pending_text_markers:
        if marker not in text:
            continue
        if has_empty_marker and marker == "处理截止时间":
            continue
        if has_empty_marker and marker in weak_markers:
            continue
        return True
    return False


def captures_indicate_non_empty_refunds(captures: list[Any]) -> bool:
    if list_capture_result(captures) == "non_empty":
        return True
    if extract_deadline_from_captures(captures).strip():
        return True

    deadline_candidate = _fallback_from_responses(captures)
    if deadline_candidate.strip():
        return True

    for capture in captures:
        if not isinstance(capture, dict):
            continue
        if list_capture_result([capture]) == "empty":
            continue
        body = capture.get("body")
        body_text = str(body)
        if any(token in body_text for token in DEFAULT_REFUND_RULES.non_empty_body_markers):
            if not any(marker in body_text for marker in DEFAULT_REFUND_RULES.zero_count_markers):
                return True
    return False


def confirm_empty_refund_list(
    *,
    page: Any,
    frame_locator: Any,
    initial_text: str,
    captures: list[Any],
    is_empty_refund_list_fn: Callable[[str], bool],
    has_pending_refund_signal_fn: Callable[[str], bool],
    captures_indicate_non_empty_refunds_fn: Callable[[list[Any]], bool],
    is_cancelled: CancelCheck | None = None,
    wait_or_cancel_fn: Callable[..., Any],
    retries: int = 6,
    interval_ms: int = 1500,
) -> tuple[bool, str]:
    latest_text = initial_text
    capture_result = list_capture_result(captures)
    if capture_result == "non_empty":
        return False, latest_text
    if capture_result == "empty" and not has_definite_pending_refund_signal(latest_text):
        for _ in range(retries):
            wait_or_cancel_fn(page, interval_ms, is_cancelled)
            latest_text = frame_locator.locator("body").text_content(timeout=15000) or ""
            capture_result = list_capture_result(captures)
            if capture_result == "non_empty":
                return False, latest_text
            if has_definite_pending_refund_signal(latest_text) or captures_indicate_non_empty_refunds_fn(captures):
                return False, latest_text
        return True, latest_text

    if has_pending_refund_signal_fn(latest_text) or captures_indicate_non_empty_refunds_fn(captures):
        return False, latest_text

    if not is_empty_refund_list_fn(latest_text):
        return False, latest_text

    for _ in range(retries):
        wait_or_cancel_fn(page, interval_ms, is_cancelled)
        latest_text = frame_locator.locator("body").text_content(timeout=15000) or ""
        capture_result = list_capture_result(captures)
        if capture_result == "non_empty":
            return False, latest_text
        if has_pending_refund_signal_fn(latest_text) or captures_indicate_non_empty_refunds_fn(captures):
            return False, latest_text
        if not is_empty_refund_list_fn(latest_text):
            return False, latest_text

    if capture_result == "empty":
        return True, latest_text
    return True, latest_text


def build_empty_refund_result(
    *,
    page: Any,
    context: Any,
    account: AccountConfig,
    output_dir: Path,
    frame_locator: Any,
    list_text: str,
    captures: list[Any],
    feedback_url: str,
    profile_dir: str,
    logger: Logger | None,
    safe_page_content_fn: Callable[..., str],
    extract_current_account_name_fn: Callable[[Any], str],
    is_cancelled: CancelCheck | None = None,
) -> FetchResult:
    actual_account_name = extract_current_account_name_fn(page)
    persist_storage_state(context, account.state_path, page=page, logger=logger, log_fn=_log)
    result = FetchResult(
        account_name=account.name,
        ok=True,
        actual_account_name=actual_account_name,
        deadline_text="",
        deadline_source="",
        matched_path="",
        page_url=feedback_url,
        note="当前账号无待处理申请。",
    )
    write_fetch_result(account.name, result)
    return result


def confirm_detail_deadline(
    *,
    page: Any,
    frame_locator: Any,
    captures: list[Any],
    feedback_url: str,
    extract_labeled_datetime_fn: Callable[[str, str], str],
    fallback_from_responses_fn: Callable[[list[Any]], str],
    filter_detail_captures_fn: Callable[[list[Any], str], list[Any]],
    wait_or_cancel_fn: Callable[..., Any],
    is_cancelled: CancelCheck | None = None,
    retries: int = 8,
    interval_ms: int = 1500,
) -> tuple[str, str, str]:
    latest_text = ""
    latest_html = ""
    deadline_text = ""

    for attempt in range(retries + 1):
        detail_captures = filter_detail_captures_fn(captures, feedback_url)
        deadline_text = extract_deadline_from_captures(detail_captures)
        if deadline_text:
            latest_text = frame_locator.locator("body").text_content(timeout=15000) or ""
            latest_html = frame_locator.locator("body").inner_html(timeout=15000)
            return deadline_text, latest_text, latest_html

        latest_text = frame_locator.locator("body").text_content(timeout=15000) or ""
        latest_html = frame_locator.locator("body").inner_html(timeout=15000)
        deadline_text = extract_labeled_datetime_fn(latest_text, "处理截止时间")
        if not deadline_text:
            deadline_text = fallback_from_responses_fn(detail_captures)
        if deadline_text:
            return deadline_text, latest_text, latest_html
        if attempt < retries:
            wait_or_cancel_fn(page, interval_ms, is_cancelled)

    return deadline_text, latest_text, latest_html


def build_detail_result(
    *,
    page: Any,
    context: Any,
    account: AccountConfig,
    output_dir: Path,
    frame_locator: Any,
    captures: list[Any],
    feedback_url: str,
    profile_dir: str,
    logger: Logger | None,
    safe_page_content_fn: Callable[..., str],
    extract_current_account_name_fn: Callable[[Any], str],
    confirm_detail_deadline_fn: Callable[..., tuple[str, str, str]],
    is_cancelled: CancelCheck | None = None,
) -> FetchResult:
    list_deadline_text = extract_deadline_from_captures(_list_captures_for_feedback_url(captures, feedback_url))
    if list_deadline_text:
        actual_account_name = extract_current_account_name_fn(page)
        persist_storage_state(context, account.state_path, page=page, logger=logger, log_fn=_log)
        result = FetchResult(
            account_name=account.name,
            ok=True,
            actual_account_name=actual_account_name,
            deadline_text=list_deadline_text,
            deadline_source="list-capture",
            matched_path="$response.list.deadline",
            page_url=feedback_url,
            note="已完成列表页抓取。",
        )
        write_fetch_result(account.name, result)
        return result

    action_locator = frame_locator.get_by_text("处理", exact=True)
    detail_capture_start = 0
    if action_locator.count():
        detail_capture_start = len(captures)
        target_action = getattr(action_locator, "last", action_locator)
        detail_capture = wait_for_action_response_contract(
            page,
            action_fn=lambda: target_action.click(timeout=10000),
            feedback_url=feedback_url,
            response_type="detail",
        )
        if detail_capture is not None:
            captures.append(detail_capture)
    deadline_text, frame_text, frame_html = confirm_detail_deadline_fn(
        page=page,
        frame_locator=frame_locator,
        captures=captures[detail_capture_start:],
        feedback_url=feedback_url,
        is_cancelled=is_cancelled,
    )
    actual_account_name = extract_current_account_name_fn(page)

    if not deadline_text:
        persist_storage_state(context, account.state_path, page=page, logger=logger, log_fn=_log)
        result = FetchResult(
            account_name=account.name,
            ok=True,
            actual_account_name=actual_account_name,
            deadline_text="",
            deadline_source="",
            matched_path="",
            page_url=feedback_url,
            note="截止时间内无待处理",
        )
        write_fetch_result(account.name, result)
        return result

    persist_storage_state(context, account.state_path, page=page, logger=logger, log_fn=_log)
    result = FetchResult(
        account_name=account.name,
        ok=True,
        actual_account_name=actual_account_name,
        deadline_text=deadline_text,
        deadline_source="iframe-label",
        matched_path="$iframeText.处理截止时间",
        page_url=feedback_url,
        note="已完成详情页抓取。",
    )
    write_fetch_result(account.name, result)
    return result


