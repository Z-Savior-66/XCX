from __future__ import annotations

from typing import Any

from desktop_py.core.session_links import propagate_account_feedback_url, sync_account_feedback_url


def select_imported_accounts(window: Any, *, selection_flag: Any) -> None:
    window.table.clearSelection()
    selected_any = False
    for row, account in enumerate(window.accounts):
        if account.is_entry_account:
            continue
        window.table.selectionModel().select(
            window.table.model().index(row, 0), selection_flag.Select | selection_flag.Rows
        )
        selected_any = True
    if not selected_any:
        window._show_info("提示", "没有可全选的导入账号。")
    window._update_action_buttons()


def save_current_settings(
    window: Any, *, app_settings_cls: Any, validate_shared_browser_profile_dir_fn: Any, save_settings_fn: Any
) -> None:
    try:
        browser_profile_dir = validate_shared_browser_profile_dir_fn(window.profile_dir_edit.text().strip())
        window.settings = app_settings_cls(
            feishu_webhook=window.webhook_edit.text().strip(),
            login_wait_seconds=window.settings.login_wait_seconds,
            headless_fetch=window.settings.headless_fetch,
            browser_profile_dir=browser_profile_dir,
            current_main_account_name=window.settings.current_main_account_name,
            auto_fetch_push_enabled=window.auto_fetch_push_switch.isChecked()
            if window.auto_fetch_push_switch is not None
            else False,
            diagnostic_retention_days=window.settings.diagnostic_retention_days,
            next_auto_renew_at=window.settings.next_auto_renew_at,
            next_auto_fetch_push_at=window.settings.next_auto_fetch_push_at,
            auto_renew_schedule_reason=window.settings.auto_renew_schedule_reason,
            auto_fetch_push_schedule_reason=window.settings.auto_fetch_push_schedule_reason,
            schedule_reason=window.settings.schedule_reason,
        )
        save_settings_fn(window.settings)
    except ValueError as exc:
        window._show_warning("参数错误", str(exc))
        return
    window.profile_dir_edit.setText(browser_profile_dir)
    window._apply_auto_fetch_push_schedule()
    window.append_log("设置已保存。")


def choose_profile_dir(window: Any, *, file_dialog: Any, prepare_shared_browser_profile_dir_fn: Any) -> None:
    target = file_dialog.getExistingDirectory(window, "选择共享浏览器资料目录", window.profile_dir_edit.text().strip())
    if target:
        try:
            profile_dir = prepare_shared_browser_profile_dir_fn(target)
        except (OSError, ValueError) as exc:
            window._show_warning("目录错误", str(exc))
            return
        window.profile_dir_edit.setText(profile_dir)


def add_account(window: Any, *, account_dialog_cls: Any, default_state_path_fn: Any, save_accounts_fn: Any) -> None:
    dialog = account_dialog_cls(parent=window)
    if dialog.exec() != dialog.DialogCode.Accepted:
        return
    account = dialog.build_account()
    if not account.name:
        window._show_warning("提示", "账号名称不能为空。")
        return
    if any(item.name == account.name for item in window.accounts):
        window._show_warning("提示", f"账号“{account.name}”已存在。")
        return
    if not account.state_path:
        account.state_path = default_state_path_fn(window.accounts)
    window.accounts.append(account)
    sync_account_feedback_url(window.accounts, account)
    propagate_account_feedback_url(window.accounts, account)
    save_accounts_fn(window.accounts)
    window.refresh_table()
    window.append_log("账号已新增。")


def edit_account(window: Any, *, account_dialog_cls: Any, default_state_path_fn: Any, save_accounts_fn: Any) -> None:
    account = window.selected_account()
    if not account:
        window._show_info("提示", "请先选择一个账号。")
        return
    if not account.is_entry_account:
        window._show_info("提示", "导入账号不允许编辑。")
        return
    dialog = account_dialog_cls(account, parent=window)
    if dialog.exec() != dialog.DialogCode.Accepted:
        return
    updated = dialog.build_account()
    if not updated.name:
        window._show_warning("提示", "账号名称不能为空。")
        return
    duplicate = any(
        (item.name == updated.name for idx, item in enumerate(window.accounts) if idx != window.selected_index())
    )
    if duplicate:
        window._show_warning("提示", f"账号“{updated.name}”已存在。")
        return
    original_state_path = account.state_path
    if not updated.state_path:
        updated.state_path = account.state_path or default_state_path_fn(window.accounts)
    if updated.state_path == original_state_path:
        updated.feedback_url = account.feedback_url
    else:
        updated.feedback_url = ""
    updated.last_login_at = account.last_login_at
    updated.last_fetch_at = account.last_fetch_at
    updated.last_deadline = account.last_deadline
    updated.last_status = account.last_status
    updated.last_note = account.last_note
    updated.session_status = account.session_status
    updated.session_source = account.session_source
    updated.last_session_verified_at = account.last_session_verified_at
    updated.last_session_renewed_at = account.last_session_renewed_at
    updated.last_session_error = account.last_session_error
    updated.last_actual_account_name = account.last_actual_account_name
    updated.session_renewal_failures = account.session_renewal_failures
    window.accounts[window.selected_index()] = updated
    sync_account_feedback_url(window.accounts, updated)
    propagate_account_feedback_url(window.accounts, updated)
    save_accounts_fn(window.accounts)
    window.refresh_table()
    window.append_log("账号已更新。")


def import_accounts(window: Any, *, fetch_switchable_accounts_fn: Any, save_accounts_fn: Any | None = None) -> None:
    base_account = window.selected_account()
    if not base_account:
        window._show_info("提示", "请先选择一个已登录的账号作为读取入口。")
        return
    if not base_account.is_entry_account:
        window._show_info("提示", "只有主账号可以导入账号列表。")
        return
    if sync_account_feedback_url(window.accounts, base_account) and callable(save_accounts_fn):
        save_accounts_fn(window.accounts)
    window._run_thread(
        lambda log: fetch_switchable_accounts_fn(
            base_account,
            headless=window.settings.headless_fetch,
            logger=log,
            profile_dir=window.settings.browser_profile_dir,
        ),
        on_success=lambda names: window._merge_imported_accounts(base_account, names),
    )


def merge_imported_accounts(
    window: Any,
    base_account: Any,
    names: list[str],
    *,
    blocked_account_names: set[str],
    account_config_cls: Any,
    save_accounts_fn: Any,
) -> None:
    existing = {account.name for account in window.accounts}
    imported = 0
    for name in names:
        if name in blocked_account_names or name in existing:
            continue
        window.accounts.append(
            account_config_cls(
                name=name,
                state_path=base_account.state_path,
                is_entry_account=False,
                feedback_url="",
                home_url=base_account.home_url,
                enabled=True,
            )
        )
        existing.add(name)
        imported += 1
    save_accounts_fn(window.accounts)
    window.refresh_table()
    window.append_log(f"已导入 {imported} 个账号。")


def delete_account(window: Any, *, message_dialog_cls: Any, save_accounts_fn: Any) -> None:
    current_indexes = window.selected_indexes()
    if not current_indexes:
        window._show_info("提示", "请先选择一个账号。")
        return
    removed_names = [window.accounts[index].name for index in current_indexes]
    if not message_dialog_cls.ask_confirm(
        window, "确认删除", f"确认删除已选中的 {len(removed_names)} 个账号吗？", confirm_text="删除", cancel_text="取消"
    ):
        return
    for index in reversed(current_indexes):
        window.accounts.pop(index)
    save_accounts_fn(window.accounts)
    window.refresh_table()
    window.append_log("账号已删除。")
