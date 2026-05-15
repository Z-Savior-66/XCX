from __future__ import annotations

from typing import Any

FETCH_MANIFEST_NAME = "fetch_manifest.json"


def fetch_selected(window: Any, *, fetch_account_fn: Any) -> None:
    account = window.selected_account()
    if not account:
        window._show_info("提示", "请先选择一个账号。")
        return
    if account.is_entry_account:
        window._show_info("提示", "主账号不参与抓取，请选择导入账号。")
        return
    window._run_thread(
        lambda log, _progress=None, is_cancelled=None: fetch_account_fn(
            account, 0, window.settings.headless_fetch, log, window.settings.browser_profile_dir, is_cancelled
        ),
        on_success=lambda result: window._mark_fetch_result(account, result),
    )


def _enabled_imported_accounts(window: Any) -> Any:
    return [account for account in window.accounts if account.enabled and (not account.is_entry_account)]


def fetch_all(window: Any) -> None:
    enabled_accounts = _enabled_imported_accounts(window)
    if not enabled_accounts:
        window._show_info("提示", "没有可抓取的导入账号。")
        return
    window._run_thread(
        window._build_fetch_job(enabled_accounts),
        on_success=lambda _results: window.append_log("批量抓取已完成。"),
        on_progress=window._mark_fetch_progress,
    )


def build_fetch_job(window: Any, enabled_accounts: list, *, fetch_accounts_batch_fn: Any) -> Any:

    def job(log: Any, progress: Any, is_cancelled: Any = None) -> Any:
        return fetch_accounts_batch_fn(
            enabled_accounts,
            headless=window.settings.headless_fetch,
            logger=log,
            progress=progress,
            profile_dir=window.settings.browser_profile_dir,
            is_cancelled=is_cancelled,
        )

    return job


def mark_fetch_progress(window: Any, result: Any) -> None:
    account = next((item for item in window.accounts if item.name == result.account_name), None)
    if account is None:
        return
    window._mark_fetch_result(account, result)


def fetch_diagnostic_message(account: Any, result: Any, *, account_output_file_fn: Any = None) -> str:
    if result.ok:
        return f"账号 {account.name} 抓取成功。"
    note = str(getattr(result, "note", "") or "").strip()
    if not note:
        note = "未返回失败原因"
    suffix = "" if note.endswith(("。", "！", "？", ".", "!", "?")) else "。"
    return f"账号 {account.name} 抓取失败：{note}{suffix}"


def mark_fetch_result(
    window: Any,
    account: Any,
    result: Any,
    *,
    apply_fetch_result_fn: Any,
    save_accounts_fn: Any,
    cleanup_account_diagnostics_fn: Any = None,
) -> None:
    current_main_account_name = apply_fetch_result_fn(account, result)
    window.append_log(fetch_diagnostic_message(account, result))
    if callable(cleanup_account_diagnostics_fn):
        try:
            cleanup_account_diagnostics_fn(
                account.name,
                retention_days=max(1, int(getattr(window.settings, "diagnostic_retention_days", 14) or 14)),
            )
        except Exception as exc:
            window.append_log(f"清理诊断产物失败：{exc}")
    window.refresh_table()
    try:
        save_accounts_fn(window.accounts)
    except Exception as exc:
        window.append_log(f"保存抓取结果失败：{exc}")
    try:
        window._update_current_main_account(current_main_account_name)
    except Exception as exc:
        window.append_log(f"更新当前主账号失败：{exc}")
    else:
        window.refresh_table()


def mark_batch_results(window: Any, results: list, *, apply_batch_fetch_results_fn: Any, save_accounts_fn: Any) -> None:
    latest_actual_account_name = apply_batch_fetch_results_fn(window.accounts, results)
    window.refresh_table()
    try:
        save_accounts_fn(window.accounts)
    except Exception as exc:
        window.append_log(f"保存批量抓取结果失败：{exc}")
    if latest_actual_account_name:
        try:
            window._update_current_main_account(latest_actual_account_name)
        except Exception as exc:
            window.append_log(f"更新当前主账号失败：{exc}")
        else:
            window.refresh_table()
    window.append_log("批量抓取已完成。")
