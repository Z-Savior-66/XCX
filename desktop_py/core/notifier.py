from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

import requests

from desktop_py.core.models import FetchResult


def send_feishu_text(webhook: str, content: str) -> None:
    if not webhook.strip():
        raise ValueError("飞书机器人地址不能为空。")
    response = requests.post(webhook, json={"msg_type": "text", "content": {"text": content}}, timeout=20)
    response.raise_for_status()
    payload = _read_feishu_response(response)
    code = _feishu_response_code(payload)
    if code != 0:
        message = str(payload.get("msg") or payload.get("message") or payload.get("StatusMessage") or "").strip()
        suffix = f"：{message}" if message else ""
        raise ValueError(f"飞书消息发送失败，业务码 {code}{suffix}")


def _read_feishu_response(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError("飞书消息发送失败：响应不是有效 JSON。") from exc
    if not isinstance(payload, dict):
        raise ValueError("飞书消息发送失败：响应内容格式不正确。")
    return payload


def _feishu_response_code(payload: dict[str, Any]) -> int:
    raw_code = payload.get("code", payload.get("StatusCode", payload.get("status_code")))
    if raw_code is None:
        raise ValueError("飞书消息发送失败：响应缺少业务状态码。")
    try:
        return int(raw_code)
    except (TypeError, ValueError) as exc:
        raise ValueError("飞书消息发送失败：响应缺少业务状态码。") from exc


def build_summary(results: list[FetchResult], generated_at: datetime | None = None) -> str:
    result_hash = summary_result_hash(results)
    generated_time = (generated_at or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    sections = [
        ("未成年退款", _refund_rows(results)),
        ("交易投诉", _transaction_complaint_rows(results)),
        ("通知中心", _notification_rows(results)),
    ]
    pending_sections = [(title, rows) for title, rows in sections if rows]
    lines = [
        "微信退款处理截止时间日报",
        f"生成时间：{generated_time}",
        f"摘要标识：{result_hash}",
        f"待处理事项：{len(pending_sections)} 类",
        "",
    ]
    if not pending_sections:
        lines.append("暂无待处理事项。")
        return "\n".join(lines)
    for section_index, (title, rows) in enumerate(pending_sections):
        if section_index > 0:
            lines.append("")
        _append_summary_section(lines, title, rows)
    return "\n".join(lines)


def _refund_rows(results: list[FetchResult]) -> list[str]:
    return [
        f"{result.account_name}：未成年申请截止 {result.deadline_text.strip()}{_actual_suffix(result)}"
        for result in sorted(results, key=_summary_sort_key)
        if _can_summarize(result) and result.deadline_text.strip()
    ]


def _transaction_complaint_rows(results: list[FetchResult]) -> list[str]:
    rows: list[str] = []
    for result in sorted(results, key=_summary_sort_key):
        summary = _transaction_complaint_summary(result)
        if _can_summarize(result) and summary:
            rows.append(f"{result.account_name}：{summary}{_actual_suffix(result)}")
    return rows


def _notification_rows(results: list[FetchResult]) -> list[str]:
    rows: list[str] = []
    for result in sorted(results, key=_summary_sort_key):
        summary = _notification_summary(result)
        if _can_summarize(result) and summary:
            rows.append(f"{result.account_name}：{summary}{_actual_suffix(result)}")
    return rows


def _append_summary_section(lines: list[str], title: str, rows: list[str]) -> None:
    lines.append(f"【{title}】")
    lines.append(f"待处理账号：{len(rows)} 个")
    for index, row in enumerate(rows, start=1):
        lines.append(f"{index}. {row}")


def _notification_summary(result: FetchResult) -> str:
    note = str(result.note or "").strip()
    if not note:
        return ""
    for segment in note.split("；"):
        value = segment.strip()
        if value.startswith("通知中心未读消息"):
            return value
    return ""


def _transaction_complaint_summary(result: FetchResult) -> str:
    note = str(result.note or "").strip()
    if not note:
        return ""
    for segment in note.split("；"):
        value = segment.strip()
        if value.startswith("交易投诉待处理"):
            return _format_transaction_complaint_summary(value)
    return ""


def _format_transaction_complaint_summary(value: str) -> str:
    prefix, separator, order_ids = value.partition("：")
    if not separator:
        return value
    return f"{prefix}，投诉编号：{order_ids.strip()}"


def _should_include_in_summary(result: FetchResult) -> bool:
    return _can_summarize(result) and bool(
        result.deadline_text.strip() or _notification_summary(result) or _transaction_complaint_summary(result)
    )


def _can_summarize(result: FetchResult) -> bool:
    if not result.account_name.strip() or not result.ok:
        return False
    return True


def _summary_sort_key(result: FetchResult) -> tuple[int, datetime, str]:
    deadline = _parse_deadline(result.deadline_text)
    if deadline is not None:
        return (0, deadline, result.account_name)
    return (1, datetime.max, result.account_name)


def _actual_suffix(result: FetchResult) -> str:
    if not result.actual_account_name or result.actual_account_name == result.account_name:
        return ""
    return f"（实际：{result.actual_account_name}）"


def _parse_deadline(deadline_text: str) -> datetime | None:
    value = deadline_text.strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def summary_result_hash(results: list[FetchResult]) -> str:
    payload = [
        {
            "account_name": result.account_name,
            "actual_account_name": result.actual_account_name,
            "deadline_text": result.deadline_text,
            "note": result.note,
            "ok": result.ok,
        }
        for result in sorted(
            results,
            key=lambda item: (
                item.account_name,
                item.actual_account_name,
                item.deadline_text,
                item.note,
                item.ok,
            ),
        )
    ]
    content = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
