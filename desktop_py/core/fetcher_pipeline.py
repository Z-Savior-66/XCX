from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from desktop_py.core.fetcher_manifest import (
    add_fetch_evidence,
    fetch_step,
    finish_fetch_run,
    start_fetch_run,
    write_fetch_manifest,
)
from desktop_py.core.fetcher_runtime import record_runtime_failure, record_runtime_success, runtime_recycle_reason
from desktop_py.core.fetcher_support import (
    CancelledError,
    FetchError,
    ensure_account_session_available,
    is_login_timeout_page,
    normalize_profile_dir,
    recover_login_timeout_page,
)
from desktop_py.core.models import AccountConfig, FetchResult
from desktop_py.core.store import write_fetch_result

BATCH_RUNTIME_REFRESH_EVERY = 5

Logger = Callable[[str], None]
CancelCheck = Callable[[], bool]
LogFn = Callable[[Logger | None, str], None]


def _prepare_account_session_for_fetch(
    account: AccountConfig,
    *,
    logger: Logger | None,
    profile_dir: str,
    headless: bool,
    log_fn: LogFn,
    validate_account_state_fn: Callable[..., bool],
    renew_account_state_fn: Callable[..., bool],
) -> None:
    session_status = account.session_status.strip()
    if not session_status or session_status == "missing":
        return
    if session_status == "stale":
        log_fn(logger, f"账号 {account.name} 登录态接近失效，先执行自动续期。")
        if renew_account_state_fn(account, logger=logger, profile_dir=profile_dir, headless=headless):
            return
        raise FetchError(f"账号 {account.name} 登录态续期失败，请重新保存登录态。")

    if validate_account_state_fn(account, logger=logger, profile_dir=profile_dir):
        return

    log_fn(logger, f"账号 {account.name} 登录态校验失败，尝试自动续期。")
    if renew_account_state_fn(account, logger=logger, profile_dir=profile_dir, headless=headless):
        return
    raise FetchError(f"账号 {account.name} 登录态无效，请重新保存登录态。")


def _page_current_account_name(page: Any) -> str:
    try:
        return str(getattr(page, "_current_account_name_cache", "") or "").strip()
    except Exception:
        return ""


def _set_page_current_account_name(page: Any, account_name: str) -> None:
    try:
        setattr(page, "_current_account_name_cache", account_name.strip())
    except Exception:
        pass


def _page_has_backend_session(page: Any) -> bool:
    try:
        current_url = str(getattr(page, "url", "") or "")
    except Exception:
        return False
    return any(keyword in current_url for keyword in ("token=", "/wxamp/index/index", "pluginRedirect/gameFeedback"))


def _wait_for_timeout(current_page: Any, wait_ms: int, _cancelled: CancelCheck | None = None) -> None:
    current_page.wait_for_timeout(wait_ms)


def _recover_timeout_page_if_needed(
    page: Any,
    *,
    logger: Logger | None,
    log_fn: LogFn,
    safe_page_content_fn: Callable[..., str],
    is_cancelled: CancelCheck | None,
) -> bool:
    return recover_login_timeout_page(
        page,
        logger=logger,
        log_fn=log_fn,
        safe_page_content_fn=safe_page_content_fn,
        wait_or_cancel_fn=_wait_for_timeout,
        is_cancelled=is_cancelled,
    )


def _set_page_home_ready(page: Any, ready: bool) -> None:
    try:
        setattr(page, "_home_ready_cache", bool(ready))
    except Exception:
        pass


def _page_home_ready(page: Any) -> bool:
    try:
        return bool(getattr(page, "_home_ready_cache", False))
    except Exception:
        return False


def resolve_bootstrap_url_impl(account: AccountConfig, output_dir: Path) -> str:
    return account.home_url


def fetch_account_in_page_impl(
    page: Any,
    context: Any,
    account: AccountConfig,
    logger: Logger | None = None,
    profile_dir: str = "",
    is_cancelled: CancelCheck | None = None,
    *,
    account_output_dir_fn: Callable[[str], Path],
    register_response_capture_fn: Callable[..., tuple[list[Any], Callable[[], None]]],
    capture_response_payload_fn: Callable[..., Any],
    resolve_bootstrap_url_fn: Callable[[AccountConfig, Path], str],
    wait_for_url_contains_fn: Callable[..., Any],
    extract_current_account_name_fn: Callable[[Any], str],
    should_switch_for_account_fn: Callable[[AccountConfig, str], bool],
    switch_to_account_fn: Callable[..., Any],
    log_fn: LogFn,
    open_feedback_page_fn: Callable[..., str],
    build_feedback_url_fn: Callable[..., str],
    wait_for_iframe_ready_fn: Callable[..., Any],
    resolve_frame_locator_fn: Callable[..., Any],
    business_iframe_selector_fn: Callable[..., str],
    safe_page_content_fn: Callable[..., str],
    fetch_notifications_fn: Callable[..., dict[str, Any]] | None = None,
    fetch_paginated_refund_list_captures_fn: Callable[..., list[Any]] | None = None,
    is_empty_refund_list_fn: Callable[..., bool],
    confirm_empty_refund_list_fn: Callable[..., tuple[bool, str]],
    build_empty_refund_result_fn: Callable[..., FetchResult],
    build_detail_result_fn: Callable[..., FetchResult],
) -> FetchResult:
    output_dir = account_output_dir_fn(account.name)
    manifest = start_fetch_run(account, profile_dir=profile_dir, output_dir=str(output_dir))

    def cleanup_response_capture() -> None:
        return None

    captures: list[Any] = []
    notification_outcome = {
        "ok": False,
        "notifications": [],
        "summary": "",
        "page_url": "",
    }

    try:
        with fetch_step(manifest, "注册响应监听"):
            captures, cleanup_response_capture = register_response_capture_fn(page, capture_response_payload_fn)

        bootstrap_url = resolve_bootstrap_url_fn(account, output_dir)
        if not _page_has_backend_session(page):
            with fetch_step(manifest, "进入微信后台", detail=bootstrap_url):
                page.goto(bootstrap_url, wait_until="domcontentloaded", timeout=60000)
                wait_for_url_contains_fn(
                    page, ("token=", "/wxamp/index/index"), timeout_ms=4000, is_cancelled=is_cancelled
                )
                _set_page_home_ready(page, bootstrap_url == account.home_url)

        with fetch_step(manifest, "检查并恢复登录超时页"):
            if is_login_timeout_page(page, safe_page_content_fn=safe_page_content_fn):
                recovered = _recover_timeout_page_if_needed(
                    page,
                    logger=logger,
                    log_fn=log_fn,
                    safe_page_content_fn=safe_page_content_fn,
                    is_cancelled=is_cancelled,
                )
                if recovered:
                    wait_for_url_contains_fn(
                        page, ("token=", "/wxamp/index/index"), timeout_ms=4000, is_cancelled=is_cancelled
                    )

        if "token=" not in page.url and bootstrap_url == account.home_url:
            raise FetchError("当前登录态未自动跳入后台页，且没有可复用的历史反馈页地址，无法启动自动切换账号。")

        with fetch_step(manifest, "确认当前账号"):
            current_account_name = _page_current_account_name(page)
            if not current_account_name:
                current_account_name = extract_current_account_name_fn(page)
                if current_account_name:
                    _set_page_current_account_name(page, current_account_name)

        with fetch_step(manifest, "切换目标账号", detail=account.name):
            if should_switch_for_account_fn(account, current_account_name):
                switch_to_account_fn(page, account.name, account.home_url, logger)
                _set_page_current_account_name(page, account.name)
            elif account.is_entry_account:
                log_fn(logger, "入口账号使用当前共享会话，不执行切换账号。")
            else:
                log_fn(logger, f"账号 {account.name} 已处于当前会话，跳过切换步骤。")

        if callable(fetch_notifications_fn):
            with fetch_step(manifest, "采集通知中心"):
                notification_outcome = fetch_notifications_fn(
                    page,
                    account=account,
                    logger=logger,
                    output_dir=output_dir,
                    log_fn=log_fn,
                    wait_for_url_contains_fn=wait_for_url_contains_fn,
                    safe_page_content_fn=safe_page_content_fn,
                    is_cancelled=is_cancelled,
                )

        feedback_capture_start = len(captures)
        with fetch_step(manifest, "打开退款反馈页"):
            feedback_url = open_feedback_page_fn(
                page,
                account=account,
                logger=logger,
                build_feedback_url_fn=build_feedback_url_fn,
                wait_for_iframe_ready_fn=wait_for_iframe_ready_fn,
                is_cancelled=is_cancelled,
            )
        current_captures = captures[feedback_capture_start:]
        if callable(fetch_paginated_refund_list_captures_fn):
            with fetch_step(manifest, "补抓退款列表分页"):
                current_captures = fetch_paginated_refund_list_captures_fn(
                    page=page,
                    captures=current_captures,
                    logger=logger,
                    log_fn=log_fn,
                )
        add_fetch_evidence(
            manifest,
            kind="network",
            label="退款反馈页响应",
            summary=f"捕获 {len(current_captures)} 条目标响应",
            metadata={"capture_count": len(current_captures)},
        )
        with fetch_step(manifest, "定位业务 iframe"):
            frame_locator = resolve_frame_locator_fn(
                page,
                output_dir=output_dir,
                business_iframe_selector_fn=business_iframe_selector_fn,
                safe_page_content_fn=safe_page_content_fn,
            )
            list_text = frame_locator.locator("body").text_content(timeout=15000) or ""

        with fetch_step(manifest, "确认退款列表状态"):
            empty_confirmed, confirmed_list_text = confirm_empty_refund_list_fn(
                page=page,
                frame_locator=frame_locator,
                initial_text=list_text,
                captures=current_captures,
                is_empty_refund_list_fn=is_empty_refund_list_fn,
                is_cancelled=is_cancelled,
            )

        if empty_confirmed:
            with fetch_step(manifest, "生成空列表采集结果"):
                result = build_empty_refund_result_fn(
                    page=page,
                    context=context,
                    account=account,
                    output_dir=output_dir,
                    frame_locator=frame_locator,
                    list_text=confirmed_list_text,
                    captures=current_captures,
                    feedback_url=feedback_url,
                    profile_dir=profile_dir,
                    logger=logger,
                    safe_page_content_fn=safe_page_content_fn,
                    extract_current_account_name_fn=extract_current_account_name_fn,
                    is_cancelled=is_cancelled,
                )
        else:
            with fetch_step(manifest, "生成详情页采集结果"):
                result = build_detail_result_fn(
                    page=page,
                    context=context,
                    account=account,
                    output_dir=output_dir,
                    frame_locator=frame_locator,
                    captures=current_captures,
                    feedback_url=feedback_url,
                    profile_dir=profile_dir,
                    logger=logger,
                    safe_page_content_fn=safe_page_content_fn,
                    extract_current_account_name_fn=extract_current_account_name_fn,
                )
        if result.actual_account_name.strip():
            _set_page_current_account_name(page, result.actual_account_name)
        notification_summary = str(notification_outcome.get("summary", "") or "").strip()
        if notification_outcome.get("notifications") or not notification_outcome.get("ok", True):
            result.note = "；".join(item for item in [result.note, notification_summary] if item)
        if notification_outcome.get("notifications"):
            write_fetch_result(account.name, result, extra={"notifications": notification_outcome["notifications"]})
        elif not notification_outcome.get("ok", True) and notification_summary:
            write_fetch_result(account.name, result)
        _set_page_home_ready(page, False)
        finish_fetch_run(manifest, result=result)
        write_fetch_manifest(account.name, manifest)
        return cast(FetchResult, result)
    except Exception as exc:
        finish_fetch_run(manifest, error=exc)
        write_fetch_manifest(account.name, manifest)
        raise
    finally:
        cleanup_response_capture()


def fetch_account_impl(
    account: AccountConfig,
    wait_seconds: int,
    headless: bool = True,
    logger: Logger | None = None,
    profile_dir: str = "",
    is_cancelled: CancelCheck | None = None,
    *,
    sync_playwright_fn: Callable[..., Any],
    path_exists_fn: Callable[[Path], bool],
    validate_shared_browser_profile_dir_fn: Callable[[str], str],
    create_browser_context_fn: Callable[..., tuple[Any | None, Any]],
    validate_account_state_fn: Callable[..., bool],
    renew_account_state_fn: Callable[..., bool],
    fetch_account_in_page_fn: Callable[..., FetchResult],
    acquire_group_runtime_fn: Callable[..., Any],
    release_group_runtime_fn: Callable[[Any], None],
    invalidate_group_runtime_fn: Callable[..., None],
    runtime_current_account_name_fn: Callable[[Any], str],
    update_runtime_current_account_name_fn: Callable[[Any, str], None],
    should_invalidate_runtime_fn: Callable[[Exception], bool],
) -> FetchResult:
    normalized_profile_dir = normalize_profile_dir(
        profile_dir,
        validate_shared_browser_profile_dir_fn=validate_shared_browser_profile_dir_fn,
    )
    ensure_account_session_available(
        account,
        normalized_profile_dir,
        path_exists_fn=path_exists_fn,
        error_cls=FetchError,
    )
    _prepare_account_session_for_fetch(
        account,
        logger=logger,
        profile_dir=normalized_profile_dir,
        headless=headless,
        log_fn=lambda current_logger, message: current_logger(message) if current_logger else None,
        validate_account_state_fn=validate_account_state_fn,
        renew_account_state_fn=renew_account_state_fn,
    )

    runtime = acquire_group_runtime_fn(
        account,
        headless=headless,
        profile_dir=normalized_profile_dir,
        sync_playwright_fn=sync_playwright_fn,
        create_browser_context_fn=create_browser_context_fn,
        logger=logger,
        is_cancelled=is_cancelled,
    )
    try:
        if runtime_current_account_name_fn(runtime):
            update_runtime_current_account_name_fn(runtime, runtime_current_account_name_fn(runtime))
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
        return cast(FetchResult, result)
    except Exception as exc:
        record_runtime_failure(runtime, exc)
        if should_invalidate_runtime_fn(exc):
            invalidate_group_runtime_fn(runtime, str(exc))
        else:
            release_group_runtime_fn(runtime)
        raise
    finally:
        if runtime.busy:
            release_group_runtime_fn(runtime)


def fetch_accounts_batch_impl(
    accounts: list[AccountConfig],
    headless: bool = True,
    logger: Logger | None = None,
    progress: Callable[[FetchResult], None] | None = None,
    profile_dir: str = "",
    is_cancelled: CancelCheck | None = None,
    *,
    sync_playwright_fn: Callable[..., Any],
    path_exists_fn: Callable[[Path], bool],
    validate_shared_browser_profile_dir_fn: Callable[[str], str],
    create_browser_context_fn: Callable[..., tuple[Any | None, Any]],
    validate_account_state_fn: Callable[..., bool],
    renew_account_state_fn: Callable[..., bool],
    fetch_account_in_page_fn: Callable[..., FetchResult],
    acquire_group_runtime_fn: Callable[..., Any],
    release_group_runtime_fn: Callable[[Any], None],
    invalidate_group_runtime_fn: Callable[..., None],
    update_runtime_current_account_name_fn: Callable[[Any, str], None],
    should_invalidate_runtime_fn: Callable[[Exception], bool],
    batch_runtime_refresh_every: int = BATCH_RUNTIME_REFRESH_EVERY,
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
    for group_accounts in grouped_accounts.values():
        if is_cancelled is not None and is_cancelled():
            raise CancelledError("任务已取消")
        primary_account = group_accounts[0]
        ensure_account_session_available(
            primary_account,
            normalized_profile_dir,
            path_exists_fn=path_exists_fn,
            error_cls=FetchError,
        )
        _prepare_account_session_for_fetch(
            primary_account,
            logger=logger,
            profile_dir=normalized_profile_dir,
            headless=headless,
            log_fn=lambda current_logger, message: current_logger(message) if current_logger else None,
            validate_account_state_fn=validate_account_state_fn,
            renew_account_state_fn=renew_account_state_fn,
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
                except CancelledError:
                    raise
                except Exception as exc:
                    record_runtime_failure(runtime, exc)
                    if should_invalidate_runtime_fn(exc):
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
                if is_cancelled is not None and is_cancelled():
                    raise CancelledError("任务已取消")
                results.append(result)
                if progress is not None:
                    progress(result)
                recycle_reason = runtime_recycle_reason(runtime, max_processed_count=batch_runtime_refresh_every)
                if recycle_reason and index < len(group_accounts) - 1:
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
            if is_cancelled is not None and is_cancelled():
                raise CancelledError("任务已取消")
        finally:
            if runtime.valid:
                invalidate_group_runtime_fn(runtime)
    return results
