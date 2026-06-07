from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from desktop_py.core.fetcher_common import Logger
from desktop_py.core.fetcher_manifest import (
    BatchDiagnosticIndex,
    FetchRunManifest,
    finish_fetch_run,
    write_batch_diagnostic_index,
    write_fetch_manifest,
)
from desktop_py.core.fetcher_routes import FeedbackRoute
from desktop_py.core.models import FetchResult
from desktop_py.core.store import write_fetch_result

LogFn = Callable[[Logger | None, str], None]


def default_notification_outcome() -> dict[str, Any]:
    return {
        "ok": False,
        "notifications": [],
        "summary": "",
        "page_url": "",
    }


def default_transaction_complaint_outcome() -> dict[str, Any]:
    return {
        "ok": True,
        "enabled": False,
        "complaints": [],
        "summary": "",
        "page_url": "",
    }


def parse_deadline_text(deadline_text: str) -> datetime | None:
    value = deadline_text.strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M")
        except ValueError:
            return None


def select_final_refund_outcome(outcomes: tuple[Any, ...]) -> Any:
    if not outcomes:
        raise ValueError("退款结果列表不能为空。")
    detailed: list[tuple[datetime, int, Any]] = []
    for index, outcome in enumerate(outcomes):
        parsed = parse_deadline_text(str(outcome.result.deadline_text))
        if parsed is not None:
            detailed.append((parsed, index, outcome))
    if detailed:
        detailed.sort(key=lambda item: (item[0], item[1]))
        return detailed[0][2]
    return outcomes[0]


def _ensure_sentence(text: str) -> str:
    value = text.strip()
    if not value:
        return ""
    if value.endswith(("。", "！", "？", ".", "!", "?")):
        return value
    return f"{value}。"


def _transaction_complaint_log_summary(transaction_complaint_outcome: dict[str, Any]) -> str:
    if not transaction_complaint_outcome.get("enabled") or not transaction_complaint_outcome.get("ok", True):
        return ""
    complaints = [
        item
        for item in transaction_complaint_outcome.get("complaints", [])
        if isinstance(item, dict) and str(item.get("complaint_order_id", "") or "").strip()
    ]
    if not complaints:
        return "交易投诉无待处理。"
    order_ids = "、".join(str(item["complaint_order_id"]).strip() for item in complaints[:3])
    suffix = " 等" if len(complaints) > 3 else ""
    return f"交易投诉待处理 {len(complaints)} 条，投诉编号：{order_ids}{suffix}。"


def build_success_log_lines(
    *,
    notification_outcome: dict[str, Any],
    transaction_complaint_outcome: dict[str, Any] | None = None,
    refund_outcomes: tuple[Any, ...],
) -> list[str]:
    lines: list[str] = []
    for outcome in refund_outcomes:
        route = outcome.route
        if not isinstance(route, FeedbackRoute):
            continue
        if route.step_label == "退款反馈页":
            if str(outcome.result.deadline_text).strip():
                lines.append(f"未成年退款申请处理截止时间：{str(outcome.result.deadline_text).strip()}。")
            else:
                lines.append("未成年退款申请截止时间内无待处理。")
        elif route.step_label == "iOS退款问询":
            if str(outcome.result.deadline_text).strip():
                lines.append(f"IOS退款问询处理截止时间：{str(outcome.result.deadline_text).strip()}。")
            else:
                lines.append("IOS退款问询当前无待处理申请。")
    transaction_complaint_summary = _transaction_complaint_log_summary(transaction_complaint_outcome or {})
    if transaction_complaint_summary:
        lines.append(transaction_complaint_summary)
    notification_summary = str(notification_outcome.get("summary", "") or "").strip()
    if notification_summary:
        lines.append(_ensure_sentence(notification_summary))
    return lines


def log_fetch_success_summary(
    *,
    account_name: str,
    logger: Logger | None,
    log_fn: LogFn,
    notification_outcome: dict[str, Any],
    transaction_complaint_outcome: dict[str, Any] | None = None,
    refund_outcomes: tuple[Any, ...],
) -> None:
    lines = build_success_log_lines(
        notification_outcome=notification_outcome,
        transaction_complaint_outcome=transaction_complaint_outcome,
        refund_outcomes=refund_outcomes,
    )
    if not lines:
        return
    summary = "\n".join(f"{index}.{line}" for index, line in enumerate(lines, start=1))
    log_fn(logger, f"账号 {account_name} 抓取成功：\n{summary}")


def compose_fetch_result(
    *,
    page: Any,
    account_name: str,
    refund_outcomes: tuple[Any, ...],
    notification_outcome: dict[str, Any],
    transaction_complaint_outcome: dict[str, Any],
    set_page_current_account_name_fn: Callable[[Any, str], None],
) -> tuple[FetchResult, dict[str, Any]]:
    if transaction_complaint_outcome.get("enabled"):
        result = FetchResult(
            account_name=account_name,
            ok=bool(transaction_complaint_outcome.get("ok", True)),
            actual_account_name=account_name,
            page_url=str(transaction_complaint_outcome.get("page_url", "") or ""),
        )
    else:
        result = select_final_refund_outcome(refund_outcomes).result

    if result.actual_account_name.strip():
        set_page_current_account_name_fn(page, result.actual_account_name.strip())

    transaction_complaint_summary = str(transaction_complaint_outcome.get("summary", "") or "").strip()
    if transaction_complaint_outcome.get("enabled") and (
        transaction_complaint_summary or not transaction_complaint_outcome.get("ok", True)
    ):
        result.note = "；".join(item for item in [result.note, transaction_complaint_summary] if item)
    notification_summary = str(notification_outcome.get("summary", "") or "").strip()
    if notification_outcome.get("notifications") or not notification_outcome.get("ok", True):
        result.note = "；".join(item for item in [result.note, notification_summary] if item)

    result_extra: dict[str, Any] = {}
    if notification_outcome.get("notifications"):
        result_extra["notifications"] = notification_outcome["notifications"]
    if transaction_complaint_outcome.get("enabled"):
        result_extra["transaction_complaints"] = transaction_complaint_outcome.get("complaints", [])
    return result, result_extra


def write_fetch_result_payload(
    account_name: str,
    result: FetchResult,
    *,
    result_extra: dict[str, Any],
    notification_outcome: dict[str, Any],
) -> None:
    if result_extra:
        write_fetch_result(account_name, result, extra=result_extra)
    elif not notification_outcome.get("ok", True) and str(notification_outcome.get("summary", "") or "").strip():
        write_fetch_result(account_name, result)


def persist_fetch_run(
    manifest: FetchRunManifest,
    *,
    account_name: str,
    result: FetchResult | None = None,
    error: Exception | None = None,
) -> None:
    finish_fetch_run(manifest, result=result, error=error)
    write_fetch_manifest(account_name, manifest)


def write_batch_diagnostic_index_safely(index: BatchDiagnosticIndex, logger: Logger | None) -> None:
    try:
        write_batch_diagnostic_index(index)
    except Exception as exc:
        if logger is not None:
            logger(f"写入批量诊断索引失败：{exc}")
