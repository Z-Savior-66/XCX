from __future__ import annotations

from typing import Any

from desktop_py.core.models import SESSION_STATUS_STALE, SESSION_STATUS_VALID
from desktop_py.core.session_links import propagate_account_feedback_url
from desktop_py.ui.common_actions import entry_account


def auto_validate_entry_account(window: Any, *, os_module: Any, validate_account_state_fn: Any) -> None:
    if os_module.environ.get("QT_QPA_PLATFORM") == "offscreen":
        return
    account = entry_account(window)
    if account is None:
        return
    account.last_status = "检测中"
    account.last_note = ""
    window.refresh_table()
    window._run_thread(
        lambda _log: safe_validate_account_state(window, account, validate_account_state_fn=validate_account_state_fn),
        on_success=lambda ok: window._mark_validation(account, bool(ok)),
        emit_log=False,
        emit_failure_log=False,
        update_status=False,
    )


def safe_validate_account_state(window: Any, account: Any, *, validate_account_state_fn: Any) -> bool:
    try:
        return bool(validate_account_state_fn(account, None, window.settings.browser_profile_dir))
    except Exception:
        return False


def account_for_auto_renew(window: Any, candidates: list | None = None) -> Any:
    current_entry_account = entry_account(window)
    if current_entry_account is not None:
        return current_entry_account
    if candidates:
        return candidates[0]
    return None


def renew_switch_account_names(window: Any, account: Any) -> list[str]:
    state_path = str(getattr(account, "state_path", "") or "").strip()
    uses_shared_profile = bool(str(getattr(getattr(window, "settings", None), "browser_profile_dir", "") or "").strip())
    names: list[str] = []
    for item in getattr(window, "accounts", []) or []:
        if item is account or bool(getattr(item, "is_entry_account", False)):
            continue
        item_name = str(getattr(item, "name", "") or "").strip()
        if not item_name or item_name in names:
            continue
        if not uses_shared_profile and state_path and str(getattr(item, "state_path", "") or "").strip() != state_path:
            continue
        if not bool(getattr(item, "enabled", True)):
            continue
        names.append(item_name)
    return names


def login_selected(window: Any, *, save_login_state_with_profile_fn: Any, save_login_state_fn: Any) -> None:
    account = window.selected_account()
    if not account:
        window._show_info("提示", "请先选择一个账号。")
        return
    if not account.is_entry_account:
        window._show_info("提示", "导入账号不能直接保存登录态，请选择入口账号。")
        return
    window.append_log(window._login_start_message(account))
    window.statusBar().showMessage("已打开浏览器，请完成扫码登录。", 8000)
    window._run_thread(
        lambda log, _progress=None, is_cancelled=None: (
            save_login_state_with_profile_fn(
                account, window.settings.login_wait_seconds, window.settings.browser_profile_dir, log, is_cancelled
            )
            if window.settings.browser_profile_dir.strip()
            else save_login_state_fn(account, window.settings.login_wait_seconds, log, is_cancelled)
        ),
        on_success=lambda _: window._mark_login(account),
    )


def mark_login(
    window: Any, account: Any, *, datetime_cls: Any, save_accounts_fn: Any, close_all_group_runtimes_fn: Any = None
) -> None:
    account.last_login_at = datetime_cls.now().strftime("%Y-%m-%d %H:%M:%S")
    account.last_status = "已保存登录态"
    account.last_note = "可继续导入账号或直接抓取"
    account.session_status = SESSION_STATUS_VALID
    account.last_session_error = ""
    for item in window.accounts:
        if item is account:
            continue
        if item.state_path == account.state_path:
            item.feedback_url = ""
    propagate_account_feedback_url(window.accounts, account)
    if callable(close_all_group_runtimes_fn):
        close_all_group_runtimes_fn()
    save_accounts_fn(window.accounts)
    window.refresh_table()
    window.append_log(f"账号 {account.name} 的登录态已保存完成。")
    window.statusBar().showMessage("登录态已保存", 5000)


def login_start_message(window: Any, account: Any) -> str:
    if window.settings.browser_profile_dir.strip():
        return f"正在为账号 {account.name} 打开共享浏览器资料目录。请在 {window.settings.login_wait_seconds} 秒内完成扫码，登录成功后保持页面打开等待自动保存。"
    return f"正在为账号 {account.name} 打开独立登录窗口。请在 {window.settings.login_wait_seconds} 秒内完成扫码，登录成功后保持页面打开等待自动保存。"


def validate_selected(window: Any, *, validate_account_state_fn: Any) -> None:
    account = window.selected_account()
    if not account:
        window._show_info("提示", "请先选择一个账号。")
        return
    if not account.is_entry_account:
        window._show_info("提示", "导入账号不能校验登录态，请选择主账号。")
        return
    window._run_thread(
        lambda log: validate_account_state_fn(account, log, window.settings.browser_profile_dir),
        on_success=lambda ok: window._mark_validation(account, bool(ok)),
    )


def renew_selected(window: Any, *, renew_account_state_fn: Any, close_all_group_runtimes_fn: Any = None) -> None:
    account = window.selected_account()
    if not account:
        window._show_info("提示", "请先选择一个账号。")
        return
    if not account.is_entry_account:
        window._show_info("提示", "导入账号不能登录续期，请选择主账号。")
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

    window._run_thread(job, on_success=lambda ok: window._mark_auto_renew_result(account, bool(ok)))


def mark_validation(window: Any, account: Any, valid: bool, *, save_accounts_fn: Any) -> None:
    account.last_status = "登录有效" if valid else "登录失效"
    if valid:
        account.last_note = (
            "可直接抓取" if account.session_status != SESSION_STATUS_STALE else "登录态接近失效，建议优先续期"
        )
    else:
        account.last_note = account.last_session_error or "请重新保存登录态"
    if valid:
        propagate_account_feedback_url(window.accounts, account)
    save_accounts_fn(window.accounts)
    window.refresh_table()
