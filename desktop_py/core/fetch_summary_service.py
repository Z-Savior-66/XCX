from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from desktop_py.core.models import FetchResult, PendingNotification
from desktop_py.core.notifier import build_pending_notification, build_summary, send_feishu_text


def send_summary_with_pending_notification(
    webhook: str,
    results: Sequence[FetchResult],
    *,
    build_summary_fn: Any = build_summary,
    send_feishu_text_fn: Any = send_feishu_text,
    build_pending_notification_fn: Any = build_pending_notification,
    append_pending_notification_fn: Any,
    pending_source: str = "飞书汇总",
) -> str:
    summary = str(build_summary_fn(list(results)))
    try:
        send_feishu_text_fn(webhook, summary)
    except Exception:
        append_pending_notification_fn(build_pending_notification_fn(summary, source=pending_source))
        raise
    return summary


def resend_pending_notifications(
    webhook: str,
    notifications: Sequence[PendingNotification],
    *,
    send_feishu_text_fn: Any = send_feishu_text,
    remove_pending_notifications_fn: Any,
) -> int:
    sent_count = 0
    for notification in notifications:
        send_feishu_text_fn(webhook, notification.content)
        remove_pending_notifications_fn([notification.id])
        sent_count += 1
    return sent_count
