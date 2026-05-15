from __future__ import annotations

from typing import Any

from desktop_py.ui.fetch_actions import _enabled_imported_accounts

AUTO_PUSH_SKIP_NOTE = "当前登录态未自动跳入后台页，且没有可复用的历史反馈页地址，无法启动自动切换账号。"


def auto_fetch_and_send(window: Any) -> None:
    webhook = window.webhook_edit.text().strip()
    window.settings.feishu_webhook = webhook
    if not webhook:
        window._show_warning("提示", "请先填写飞书 Webhook。")
        return
    enabled_accounts = _enabled_imported_accounts(window)
    if not enabled_accounts:
        window._show_info("提示", "没有可抓取的导入账号。")
        return
    window._run_thread(
        window._build_fetch_job(enabled_accounts),
        on_success=lambda results: _handle_auto_summary_after_fetch(window, webhook, results),
        on_progress=window._mark_fetch_progress,
    )


def should_skip_auto_summary_for_results(results: list) -> bool:
    if not results:
        return False
    return all(str(getattr(result, "note", "") or "").strip() == AUTO_PUSH_SKIP_NOTE for result in results)


def _handle_auto_summary_after_fetch(window: Any, webhook: str, results: list) -> None:
    if should_skip_auto_summary_for_results(results):
        window.append_log("批量抓取已完成。")
        window.append_log("自动抓取推送已跳过：当前登录态未进入后台页，且没有可复用的历史反馈页地址。")
        return
    window._send_summary_with_webhook(webhook, append_batch_log=True)


def send_summary(window: Any) -> None:
    webhook = window.webhook_edit.text().strip()
    window.settings.feishu_webhook = webhook
    if not webhook:
        window._show_warning("提示", "请先填写飞书 Webhook。")
        return
    window._send_summary_with_webhook(webhook)


def send_summary_with_webhook(
    window: Any,
    webhook: str,
    append_batch_log: bool = False,
    *,
    build_summary_fn: Any,
    send_feishu_text_fn: Any,
    fetch_result_cls: Any,
    actual_account_prefix: str,
    save_accounts_fn: Any,
) -> None:
    if append_batch_log:
        window.append_log("批量抓取已完成。")
    results = [
        fetch_result_cls(
            account_name=account.name,
            ok=account.last_status == "抓取成功",
            actual_account_name=actual_account_name_from_note(
                account.last_note, actual_account_prefix=actual_account_prefix
            ),
            deadline_text=account.last_deadline,
            note=account.last_note,
            page_url=account.home_url,
        )
        for account in window.accounts
        if account.enabled
    ]
    window._run_thread(
        lambda _log: send_feishu_text_fn(webhook, build_summary_fn(results)),
        on_success=lambda _: clear_pushed_fetch_state(window, save_accounts_fn=save_accounts_fn),
    )


def clear_pushed_fetch_state(window: Any, *, save_accounts_fn: Any) -> None:
    for account in window.accounts:
        if account.is_entry_account or not account.enabled:
            continue
        if account.last_status != "抓取成功":
            continue
        account.last_deadline = ""
        account.last_status = ""
        account.last_note = ""
    window.refresh_table()
    try:
        save_accounts_fn(window.accounts)
    except Exception as exc:
        window.append_log(f"清理推送后状态失败：{exc}")
    window.append_log("飞书汇总已发送。")
    window.append_log("已清理推送后的抓取状态。")


def actual_account_name_from_note(note: str, *, actual_account_prefix: str) -> str:
    for part in note.split("；"):
        text = part.strip()
        if text.startswith(actual_account_prefix):
            return text.removeprefix(actual_account_prefix).strip()
    return ""
