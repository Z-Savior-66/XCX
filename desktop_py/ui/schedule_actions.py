from __future__ import annotations

import os
import random
from typing import Any

from desktop_py.core.schedule_state_service import (
    AUTO_RENEW_BUSY_RETRY_MS,
)
from desktop_py.core.schedule_state_service import (
    auto_renew_schedule_interval as auto_renew_schedule_interval_service,
)
from desktop_py.core.schedule_state_service import (
    format_interval as format_interval_service,
)
from desktop_py.core.schedule_state_service import (
    format_next_schedule_time as format_next_schedule_time_service,
)
from desktop_py.core.schedule_state_service import (
    persist_schedule_state as persist_schedule_state_service,
)
from desktop_py.core.session_persistence import analyze_storage_state
from desktop_py.ui.fetch_actions import _enabled_imported_accounts
from desktop_py.ui.notification_actions import _handle_auto_summary_after_fetch
from desktop_py.ui.session_actions import account_for_auto_renew, renew_switch_account_names


def schedule_startup_jobs(window: Any, *, timer_cls: Any) -> None:
    timer_cls.singleShot(0, window._run_auto_renew)
    timer_cls.singleShot(0, window._auto_validate_entry_account)
    timer_cls.singleShot(0, window._apply_auto_fetch_push_schedule)
    timer_cls.singleShot(0, window._apply_auto_renew_schedule)


def handle_auto_fetch_push_toggled(window: Any, checked: bool, *, save_settings_fn: Any) -> None:
    window.settings.auto_fetch_push_enabled = checked
    save_settings_fn(window.settings)
    if checked:
        window.append_log("已开启自动抓取推送，每天 09:00 自动执行。")
    else:
        window.append_log("已关闭自动抓取推送。")
    window._apply_auto_fetch_push_schedule()


def _format_next_schedule_time(interval_ms: int, *, now_fn: Any = None) -> str:
    return format_next_schedule_time_service(interval_ms, now_fn=now_fn)


def _persist_schedule_state(
    window: Any,
    *,
    save_schedule_state_fn: Any = None,
    next_auto_renew_at: str | None = None,
    next_auto_fetch_push_at: str | None = None,
    auto_renew_schedule_reason: str | None = None,
    auto_fetch_push_schedule_reason: str | None = None,
    schedule_reason: str | None = None,
) -> None:
    persist_schedule_state_service(
        window.schedule_state,
        save_schedule_state_fn=save_schedule_state_fn,
        next_auto_renew_at=next_auto_renew_at,
        next_auto_fetch_push_at=next_auto_fetch_push_at,
        auto_renew_schedule_reason=auto_renew_schedule_reason,
        auto_fetch_push_schedule_reason=auto_fetch_push_schedule_reason,
        schedule_reason=schedule_reason,
    )


def apply_auto_fetch_push_schedule(window: Any, *, save_schedule_state_fn: Any = None, now_fn: Any = None) -> None:
    window._auto_fetch_timer.stop()
    if not window.settings.auto_fetch_push_enabled:
        _persist_schedule_state(
            window,
            save_schedule_state_fn=save_schedule_state_fn,
            next_auto_fetch_push_at="",
            auto_fetch_push_schedule_reason="自动抓取推送未开启",
            schedule_reason="自动抓取推送未开启",
        )
        return
    interval = window._milliseconds_until_next_auto_fetch_push()
    window._auto_fetch_timer.start(interval)
    reason = "每天 09:00 自动执行"
    _persist_schedule_state(
        window,
        save_schedule_state_fn=save_schedule_state_fn,
        next_auto_fetch_push_at=_format_next_schedule_time(interval, now_fn=now_fn),
        auto_fetch_push_schedule_reason=reason,
        schedule_reason=reason,
    )


def milliseconds_until_next_auto_fetch_push(window: Any, now: Any = None, *, next_interval_fn: Any) -> int:
    return int(next_interval_fn(now))


def handle_auto_fetch_push_timeout(window: Any) -> None:
    window._apply_auto_fetch_push_schedule()
    window._run_auto_fetch_push()


def _format_interval(interval_ms: int) -> str:
    return format_interval_service(interval_ms)


def auto_renew_schedule_interval(
    account: Any,
    *,
    min_auto_renew_interval_ms: int,
    max_auto_renew_interval_ms: int,
    random_int_fn: Any = None,
    analyze_storage_state_fn: Any = None,
) -> tuple[int, str]:
    return auto_renew_schedule_interval_service(
        account,
        min_auto_renew_interval_ms=min_auto_renew_interval_ms,
        max_auto_renew_interval_ms=max_auto_renew_interval_ms,
        random_int_fn=random_int_fn or random.randint,
        analyze_storage_state_fn=analyze_storage_state_fn or analyze_storage_state,
    )


def apply_auto_renew_schedule(
    window: Any,
    *,
    min_auto_renew_interval_ms: int,
    max_auto_renew_interval_ms: int,
    save_schedule_state_fn: Any = None,
    now_fn: Any = None,
) -> None:
    window._auto_renew_timer.stop()
    interval, reason = auto_renew_schedule_interval(
        account_for_auto_renew(window),
        min_auto_renew_interval_ms=min_auto_renew_interval_ms,
        max_auto_renew_interval_ms=max_auto_renew_interval_ms,
    )
    window._auto_renew_timer.start(interval)
    _persist_schedule_state(
        window,
        save_schedule_state_fn=save_schedule_state_fn,
        next_auto_renew_at=_format_next_schedule_time(interval, now_fn=now_fn),
        auto_renew_schedule_reason=reason,
        schedule_reason=reason,
    )
    if callable(getattr(window, "append_log", None)):
        window.append_log(f"自动续期下次将在约 {_format_interval(interval)} 后执行：{reason}。")


def handle_auto_renew_timeout(window: Any) -> None:
    window._apply_auto_renew_schedule()
    window._run_auto_renew()


def run_auto_renew(
    window: Any,
    *,
    renew_account_state_fn: Any,
    close_all_group_runtimes_fn: Any = None,
    save_schedule_state_fn: Any = None,
    now_fn: Any = None,
) -> None:
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        return
    if window._threads:
        window.append_log("自动续期已跳过：当前存在后台任务。")
        window._auto_renew_timer.stop()
        window._auto_renew_timer.start(AUTO_RENEW_BUSY_RETRY_MS)
        reason = "当前存在后台任务，自动续期延后重试"
        _persist_schedule_state(
            window,
            save_schedule_state_fn=save_schedule_state_fn,
            next_auto_renew_at=_format_next_schedule_time(AUTO_RENEW_BUSY_RETRY_MS, now_fn=now_fn),
            auto_renew_schedule_reason=reason,
            schedule_reason=reason,
        )
        window.append_log(f"自动续期已重排到约 {_format_interval(AUTO_RENEW_BUSY_RETRY_MS)} 后重试。")
        return
    account = account_for_auto_renew(window)
    if account is None:
        window.append_log("自动续期已跳过：未配置主账号。")
        return

    def job(log: Any) -> Any:
        if callable(close_all_group_runtimes_fn):
            close_all_group_runtimes_fn()
        return renew_account_state_fn(
            account,
            log,
            window.settings.browser_profile_dir,
            window.settings.headless_fetch,
            renew_switch_account_names(window, account),
        )

    window._run_thread(
        job, on_success=lambda ok: window._mark_auto_renew_result(account, bool(ok)), update_status=False
    )


def mark_auto_renew_result(window: Any, account: Any, valid: bool, *, save_accounts_fn: Any) -> None:
    account.last_status = "登录有效" if valid else "登录失效"
    account.session_renewal_failures = 0 if valid else int(getattr(account, "session_renewal_failures", 0) or 0) + 1
    if valid:
        account.last_note = "自动续期成功，保存后复验通过，可直接抓取"
        renewed_at = getattr(account, "last_session_renewed_at", "") or "刚刚"
        window.append_log(f"自动续期已通过保存后复验，最近续期时间：{renewed_at}。")
    else:
        base_reason = account.last_session_error or "自动续期失败，请重新保存登录态"
        account.last_note = f"{base_reason}，连续失败 {account.session_renewal_failures} 次"
        window.append_log(f"自动续期失败，连续失败 {account.session_renewal_failures} 次：{base_reason}。")
    save_accounts_fn(window.accounts)
    window.refresh_table()


def run_auto_fetch_push(window: Any) -> None:
    if window._threads:
        window.append_log("自动抓取推送已跳过：当前存在后台任务。")
        return
    webhook_edit = getattr(window, "webhook_edit", None)
    webhook_text = webhook_edit.text().strip() if webhook_edit is not None else ""
    webhook = webhook_text or window.settings.feishu_webhook.strip()
    if not webhook:
        window.append_log("自动抓取推送已跳过：未配置飞书 Webhook。")
        return
    enabled_accounts = _enabled_imported_accounts(window)
    if not enabled_accounts:
        window.append_log("自动抓取推送已跳过：没有可抓取的导入账号。")
        return
    window.settings.feishu_webhook = webhook
    window.append_log("开始执行每日自动抓取推送。")
    window._run_thread(
        window._build_fetch_job(enabled_accounts),
        on_success=lambda results: _handle_auto_summary_after_fetch(window, webhook, results),
        on_progress=window._mark_fetch_progress,
    )
