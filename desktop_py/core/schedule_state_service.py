from __future__ import annotations

import random
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from desktop_py.core.models import SESSION_STATUS_STALE, ScheduleState
from desktop_py.core.session_persistence import analyze_storage_state

AUTO_RENEW_BUSY_RETRY_MS = 10 * 60 * 1000
AUTO_RENEW_EXPIRED_RETRY_MS = 5 * 60 * 1000
AUTO_RENEW_STALE_RETRY_MS = 15 * 60 * 1000
AUTO_RENEW_EXPIRING_SOON_SECONDS = 6 * 60 * 60
AUTO_RENEW_WATCH_WINDOW_SECONDS = 24 * 60 * 60
AUTO_RENEW_MAX_BACKOFF_MS = 12 * 60 * 60 * 1000
SCHEDULE_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def next_auto_fetch_push_interval_ms(now: datetime | None = None) -> int:
    current = now or datetime.now()
    target = current.replace(hour=9, minute=0, second=0, microsecond=0)
    if current >= target:
        target += timedelta(days=1)
    return max(int((target - current).total_seconds() * 1000), 1)


def format_next_schedule_time(interval_ms: int, *, now_fn: Callable[[], datetime] | None = None) -> str:
    if now_fn is None:
        now_fn = datetime.now
    next_time = now_fn() + timedelta(milliseconds=max(0, interval_ms))
    return next_time.strftime(SCHEDULE_TIME_FORMAT)


def persist_schedule_state(
    schedule_state: ScheduleState,
    *,
    save_schedule_state_fn: Any = None,
    next_auto_renew_at: str | None = None,
    next_auto_fetch_push_at: str | None = None,
    auto_renew_schedule_reason: str | None = None,
    auto_fetch_push_schedule_reason: str | None = None,
    schedule_reason: str | None = None,
) -> None:
    if next_auto_renew_at is not None:
        schedule_state.next_auto_renew_at = next_auto_renew_at
    if next_auto_fetch_push_at is not None:
        schedule_state.next_auto_fetch_push_at = next_auto_fetch_push_at
    if auto_renew_schedule_reason is not None:
        schedule_state.auto_renew_schedule_reason = auto_renew_schedule_reason
    if auto_fetch_push_schedule_reason is not None:
        schedule_state.auto_fetch_push_schedule_reason = auto_fetch_push_schedule_reason
    if schedule_reason is not None:
        schedule_state.schedule_reason = schedule_reason
    if callable(save_schedule_state_fn):
        save_schedule_state_fn(schedule_state)


def auto_renew_schedule_interval(
    account: Any,
    *,
    min_auto_renew_interval_ms: int,
    max_auto_renew_interval_ms: int,
    random_int_fn: Any = None,
    analyze_storage_state_fn: Any = None,
) -> tuple[int, str]:
    if random_int_fn is None:
        random_int_fn = random.randint
    if analyze_storage_state_fn is None:
        analyze_storage_state_fn = analyze_storage_state
    if account is None:
        return (
            random_int_fn(min_auto_renew_interval_ms, max_auto_renew_interval_ms),
            "未配置主账号，使用常规巡检间隔",
        )

    failures = int(getattr(account, "session_renewal_failures", 0) or 0)
    if failures >= 3:
        backoff = min(AUTO_RENEW_MAX_BACKOFF_MS, max_auto_renew_interval_ms * failures)
        return backoff, f"连续续期失败 {failures} 次，进入失败退避"

    try:
        health = analyze_storage_state_fn(account.state_path)
    except Exception as exc:
        return max_auto_renew_interval_ms, f"登录态健康诊断失败：{exc}"

    remaining = health.min_cookie_seconds_remaining
    if remaining is not None:
        if remaining <= 0:
            return AUTO_RENEW_EXPIRED_RETRY_MS, "微信后台 Cookie 已过期，优先重试续期"
        if remaining <= AUTO_RENEW_EXPIRING_SOON_SECONDS:
            interval = max(AUTO_RENEW_EXPIRED_RETRY_MS, int(remaining * 500))
            return interval, f"微信后台 Cookie 剩余 {remaining} 秒，提前续期"
        if remaining <= AUTO_RENEW_WATCH_WINDOW_SECONDS:
            interval = max(
                min_auto_renew_interval_ms,
                min(max_auto_renew_interval_ms, int((remaining - AUTO_RENEW_EXPIRING_SOON_SECONDS) * 1000)),
            )
            return interval, "微信后台 Cookie 将在 24 小时内到期，按剩余寿命调度"

    if getattr(account, "session_status", "") == SESSION_STATUS_STALE:
        return AUTO_RENEW_STALE_RETRY_MS, "登录态已接近失效，优先续期"

    if failures > 0:
        backoff = min(AUTO_RENEW_MAX_BACKOFF_MS, max_auto_renew_interval_ms * (failures + 1))
        return backoff, f"续期失败 {failures} 次，延后重试"

    return random_int_fn(min_auto_renew_interval_ms, max_auto_renew_interval_ms), health.reason or "常规自动续期巡检"


def format_interval(interval_ms: int) -> str:
    minutes = max(1, round(interval_ms / 60000))
    if minutes < 60:
        return f"{minutes} 分钟"
    hours = minutes / 60
    return f"{hours:.1f} 小时"
