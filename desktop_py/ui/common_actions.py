from __future__ import annotations

from typing import Any

from desktop_py.core.session_links import normalize_group_feedback_urls


def initialize_window_state(
    window: Any,
    *,
    ensure_runtime_dirs_fn: Any,
    load_accounts_fn: Any,
    load_settings_fn: Any,
    save_accounts_fn: Any,
    reset_current_main_account_name_fn: Any,
) -> None:
    ensure_runtime_dirs_fn()
    window.accounts = load_accounts_fn()
    if normalize_group_feedback_urls(window.accounts):
        try:
            save_accounts_fn(window.accounts)
        except PermissionError:
            pass
    window.settings = load_settings_fn()
    reset_current_main_account_name_fn()


def entry_account(window: Any) -> Any:
    return next((item for item in window.accounts if item.is_entry_account), None)


def selected_index(window: Any) -> int:
    selected = window.table.selectionModel().selectedRows()
    return selected[0].row() if selected else -1


def selected_indexes(window: Any) -> list[int]:
    selected = window.table.selectionModel().selectedRows()
    return sorted(item.row() for item in selected)


def selected_account(window: Any) -> Any:
    index = window.selected_index()
    return window.accounts[index] if 0 <= index < len(window.accounts) else None


def handle_selection_changed(window: Any) -> None:
    window.table.viewport().update()
    window._update_action_buttons()


def update_action_buttons(window: Any) -> None:
    current_indexes = window.selected_indexes()
    single_selected = len(current_indexes) == 1
    account = window.accounts[current_indexes[0]] if single_selected else None
    if window.login_button is not None:
        window.login_button.setEnabled(bool(account and account.is_entry_account))
    if window.renew_button is not None:
        window.renew_button.setEnabled(bool(account and account.is_entry_account))
    if window.edit_button is not None:
        window.edit_button.setEnabled(bool(account and account.is_entry_account))
    if window.import_button is not None:
        window.import_button.setEnabled(bool(account and account.is_entry_account))
    if window.validate_button is not None:
        window.validate_button.setEnabled(bool(account and account.is_entry_account))
    if window.fetch_selected_button is not None:
        window.fetch_selected_button.setEnabled(bool(account and (not account.is_entry_account)))
    if window.delete_button is not None:
        window.delete_button.setEnabled(bool(current_indexes))
    if window.stop_fetch_button is not None:
        window.stop_fetch_button.setEnabled(bool(window._threads))


def stop_fetching(window: Any) -> None:
    if not window._threads:
        window._show_info("提示", "当前没有正在执行的抓取或推送任务。")
        return
    window._task_runner.cancel_all()
    window._update_action_buttons()
    window.append_log("已请求停止当前后台抓取任务，正在等待当前任务退出。")
    window.statusBar().showMessage("正在停止后台任务", 4000)
    window._set_status_text("正在停止后台任务")


def update_current_main_account(window: Any, account_name: str, *, save_settings_fn: Any) -> None:
    current_name = account_name.strip()
    if not current_name:
        return
    window.settings.current_main_account_name = current_name
    save_settings_fn(window.settings)


def reset_current_main_account_name(window: Any, *, save_settings_fn: Any) -> None:
    if not window.settings.current_main_account_name.strip():
        return
    window.settings.current_main_account_name = ""
    save_settings_fn(window.settings)


def run_thread(
    window: Any,
    job_builder: Any,
    on_success: Any,
    *,
    emit_log: bool = True,
    emit_failure_log: bool = True,
    update_status: bool = True,
    on_progress: Any = None,
) -> None:
    window._task_runner.run(
        job_builder,
        on_success,
        emit_log=emit_log,
        emit_failure_log=emit_failure_log,
        update_status=update_status,
        on_progress=on_progress,
    )


def handle_thread_finished(window: Any, thread: Any) -> None:
    window._task_runner.handle_finished(thread)
