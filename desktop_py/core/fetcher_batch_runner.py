from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from desktop_py.core.fetcher_common import CancelCheck, Logger
from desktop_py.core.fetcher_manifest import (
    BatchDiagnosticIndex,
    add_batch_diagnostic_account,
    finish_batch_diagnostic_index,
    start_batch_diagnostic_index,
)
from desktop_py.core.fetcher_runtime import record_runtime_failure, record_runtime_success, runtime_recycle_reason
from desktop_py.core.fetcher_support import (
    CancelledError,
    FetchError,
    ensure_account_session_available,
    normalize_profile_dir,
)
from desktop_py.core.models import AccountConfig, FetchResult
from desktop_py.core.store import account_output_file

Progress = Callable[[FetchResult], None]


def run_fetch_accounts_batch(
    accounts: list[AccountConfig],
    *,
    headless: bool,
    logger: Logger | None,
    progress: Progress | None,
    profile_dir: str,
    is_cancelled: CancelCheck | None,
    sync_playwright_fn: Callable[..., Any],
    path_exists_fn: Callable[[Path], bool],
    validate_shared_browser_profile_dir_fn: Callable[[str], str],
    create_browser_context_fn: Callable[..., tuple[Any | None, Any]],
    prepare_account_session_fn: Callable[..., None],
    fetch_account_in_page_fn: Callable[..., FetchResult],
    acquire_group_runtime_fn: Callable[..., Any],
    invalidate_group_runtime_fn: Callable[..., None],
    update_runtime_current_account_name_fn: Callable[[Any, str], None],
    should_invalidate_runtime_fn: Callable[[Exception], bool],
    write_batch_diagnostic_index_safely_fn: Callable[[BatchDiagnosticIndex, Logger | None], None],
    batch_runtime_refresh_every: int,
) -> list[FetchResult]:
    normalized_profile_dir = normalize_profile_dir(
        profile_dir,
        validate_shared_browser_profile_dir_fn=validate_shared_browser_profile_dir_fn,
    )
    enabled_accounts = [account for account in accounts if account.enabled and not account.is_entry_account]
    if not enabled_accounts:
        return []

    grouped_accounts: dict[str, list[AccountConfig]] = {}
    for account in enabled_accounts:
        group_key = normalized_profile_dir or account.state_path
        grouped_accounts.setdefault(group_key, []).append(account)

    results: list[FetchResult] = []
    batch_index = start_batch_diagnostic_index(
        total_accounts=len(enabled_accounts),
        profile_dir=normalized_profile_dir,
    )
    try:
        for group_accounts in grouped_accounts.values():
            if is_cancelled is not None and is_cancelled():
                raise CancelledError("任务已取消")
            _process_account_group(
                group_accounts,
                normalized_profile_dir=normalized_profile_dir,
                headless=headless,
                logger=logger,
                progress=progress,
                is_cancelled=is_cancelled,
                sync_playwright_fn=sync_playwright_fn,
                path_exists_fn=path_exists_fn,
                create_browser_context_fn=create_browser_context_fn,
                prepare_account_session_fn=prepare_account_session_fn,
                fetch_account_in_page_fn=fetch_account_in_page_fn,
                acquire_group_runtime_fn=acquire_group_runtime_fn,
                invalidate_group_runtime_fn=invalidate_group_runtime_fn,
                update_runtime_current_account_name_fn=update_runtime_current_account_name_fn,
                should_invalidate_runtime_fn=should_invalidate_runtime_fn,
                batch_runtime_refresh_every=batch_runtime_refresh_every,
                batch_index=batch_index,
                results=results,
            )
    except Exception as exc:
        finish_batch_diagnostic_index(batch_index, error=exc)
        write_batch_diagnostic_index_safely_fn(batch_index, logger)
        raise
    finish_batch_diagnostic_index(batch_index)
    write_batch_diagnostic_index_safely_fn(batch_index, logger)
    return results


def _process_account_group(
    group_accounts: list[AccountConfig],
    *,
    normalized_profile_dir: str,
    headless: bool,
    logger: Logger | None,
    progress: Progress | None,
    is_cancelled: CancelCheck | None,
    sync_playwright_fn: Callable[..., Any],
    path_exists_fn: Callable[[Path], bool],
    create_browser_context_fn: Callable[..., tuple[Any | None, Any]],
    prepare_account_session_fn: Callable[..., None],
    fetch_account_in_page_fn: Callable[..., FetchResult],
    acquire_group_runtime_fn: Callable[..., Any],
    invalidate_group_runtime_fn: Callable[..., None],
    update_runtime_current_account_name_fn: Callable[[Any, str], None],
    should_invalidate_runtime_fn: Callable[[Exception], bool],
    batch_runtime_refresh_every: int,
    batch_index: BatchDiagnosticIndex,
    results: list[FetchResult],
) -> None:
    primary_account = group_accounts[0]
    ensure_account_session_available(
        primary_account,
        normalized_profile_dir,
        path_exists_fn=path_exists_fn,
        error_cls=FetchError,
    )
    prepare_account_session_fn(
        primary_account,
        logger=logger,
        profile_dir=normalized_profile_dir,
        headless=headless,
    )
    runtime = acquire_group_runtime_fn(
        primary_account,
        headless=headless,
        profile_dir=normalized_profile_dir,
        sync_playwright_fn=sync_playwright_fn,
        create_browser_context_fn=create_browser_context_fn,
        logger=logger,
        is_cancelled=is_cancelled,
    )
    try:
        for index, account in enumerate(group_accounts):
            if is_cancelled is not None and is_cancelled():
                raise CancelledError("任务已取消")
            has_next_account = index < len(group_accounts) - 1
            runtime = _process_single_account(
                runtime,
                account=account,
                primary_account=primary_account,
                normalized_profile_dir=normalized_profile_dir,
                headless=headless,
                logger=logger,
                progress=progress,
                is_cancelled=is_cancelled,
                sync_playwright_fn=sync_playwright_fn,
                create_browser_context_fn=create_browser_context_fn,
                fetch_account_in_page_fn=fetch_account_in_page_fn,
                acquire_group_runtime_fn=acquire_group_runtime_fn,
                invalidate_group_runtime_fn=invalidate_group_runtime_fn,
                update_runtime_current_account_name_fn=update_runtime_current_account_name_fn,
                should_invalidate_runtime_fn=should_invalidate_runtime_fn,
                batch_runtime_refresh_every=batch_runtime_refresh_every,
                batch_index=batch_index,
                results=results,
                has_next_account=has_next_account,
            )
            if is_cancelled is not None and is_cancelled():
                raise CancelledError("任务已取消")
    finally:
        if runtime.valid:
            invalidate_group_runtime_fn(runtime)


def _process_single_account(
    runtime: Any,
    *,
    account: AccountConfig,
    primary_account: AccountConfig,
    normalized_profile_dir: str,
    headless: bool,
    logger: Logger | None,
    progress: Progress | None,
    is_cancelled: CancelCheck | None,
    sync_playwright_fn: Callable[..., Any],
    create_browser_context_fn: Callable[..., tuple[Any | None, Any]],
    fetch_account_in_page_fn: Callable[..., FetchResult],
    acquire_group_runtime_fn: Callable[..., Any],
    invalidate_group_runtime_fn: Callable[..., None],
    update_runtime_current_account_name_fn: Callable[[Any, str], None],
    should_invalidate_runtime_fn: Callable[[Exception], bool],
    batch_runtime_refresh_every: int,
    batch_index: BatchDiagnosticIndex,
    results: list[FetchResult],
    has_next_account: bool,
) -> Any:
    account_started = time.monotonic()
    account_error: BaseException | None = None
    try:
        result = fetch_account_in_page_fn(
            runtime.page,
            runtime.context,
            account,
            logger,
            normalized_profile_dir,
            is_cancelled,
        )
        if result.actual_account_name.strip():
            update_runtime_current_account_name_fn(runtime, result.actual_account_name)
        record_runtime_success(runtime)
    except CancelledError as exc:
        add_batch_diagnostic_account(
            batch_index,
            account_name=account.name,
            error=exc,
            duration_ms=int((time.monotonic() - account_started) * 1000),
            manifest_path=str(account_output_file(account.name, "fetch_manifest.json")),
            result_path=str(account_output_file(account.name, "result.json")),
        )
        raise
    except Exception as exc:
        account_error = exc
        record_runtime_failure(runtime, exc)
        if should_invalidate_runtime_fn(exc):
            if logger is not None:
                logger(f"BATCH 账号 {account.name} 触发运行时重建：{exc}")
            invalidate_group_runtime_fn(runtime, str(exc))
            if has_next_account:
                runtime = acquire_group_runtime_fn(
                    primary_account,
                    headless=headless,
                    profile_dir=normalized_profile_dir,
                    sync_playwright_fn=sync_playwright_fn,
                    create_browser_context_fn=create_browser_context_fn,
                    logger=logger,
                    is_cancelled=is_cancelled,
                )
        result = FetchResult(account_name=account.name, ok=False, note=str(exc))
    add_batch_diagnostic_account(
        batch_index,
        account_name=account.name,
        result=result,
        error=account_error,
        duration_ms=int((time.monotonic() - account_started) * 1000),
        manifest_path=str(account_output_file(account.name, "fetch_manifest.json")),
        result_path=str(account_output_file(account.name, "result.json")),
    )
    if is_cancelled is not None and is_cancelled():
        raise CancelledError("任务已取消")
    results.append(result)
    if progress is not None:
        progress(result)
    recycle_reason = runtime_recycle_reason(runtime, max_processed_count=batch_runtime_refresh_every)
    if recycle_reason and has_next_account:
        invalidate_group_runtime_fn(runtime, recycle_reason)
        runtime = acquire_group_runtime_fn(
            primary_account,
            headless=headless,
            profile_dir=normalized_profile_dir,
            sync_playwright_fn=sync_playwright_fn,
            create_browser_context_fn=create_browser_context_fn,
            logger=logger,
            is_cancelled=is_cancelled,
        )
    return runtime
