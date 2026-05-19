from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from desktop_py.core.models import FetchResult
from desktop_py.core.notifier import build_summary, send_feishu_text


def send_summary(
    webhook: str,
    results: Sequence[FetchResult],
    *,
    build_summary_fn: Any = build_summary,
    send_feishu_text_fn: Any = send_feishu_text,
) -> str:
    summary = str(build_summary_fn(list(results)))
    send_feishu_text_fn(webhook, summary)
    return summary
