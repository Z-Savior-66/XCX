from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from desktop_py.core.fetcher_batch_runner import run_fetch_accounts_batch
from desktop_py.core.fetcher_context import PipelineContext
from desktop_py.core.fetcher_diagnostics import (
    compose_fetch_result,
    default_notification_outcome,
    default_transaction_complaint_outcome,
    log_fetch_success_summary,
    persist_fetch_run,
    write_batch_diagnostic_index_safely,
    write_fetch_result_payload,
)
from desktop_py.core.fetcher_manifest import (
    FetchRunManifest,
    add_fetch_evidence,
    fetch_step,
    start_fetch_run,
)
from desktop_py.core.fetcher_navigation import (
    collect_ios_refund_subject_captures,
    page_current_account_name,
    page_has_backend_session,
    recover_timeout_page_if_needed,
    set_page_current_account_name,
    set_page_home_ready,
    wait_for_timeout,
)
from desktop_py.core.fetcher_routes import CollectionRoute, FeedbackRoute
from desktop_py.core.fetcher_runtime import record_runtime_failure, record_runtime_success
from desktop_py.core.fetcher_support import (
    FetchError,
    FetchErrorCode,
    ensure_account_session_available,
    is_login_timeout_page,
    normalize_profile_dir,
)
from desktop_py.core.models import AccountConfig, FetchResult

BATCH_RUNTIME_REFRESH_EVERY = 5

Logger = Callable[[str], None]
CancelCheck = Callable[[], bool]
LogFn = Callable[[Logger | None, str], None]


@dataclass(frozen=True)
class _RefundFeedbackFlow:
    empty_confirmed: bool
    confirmed_list_text: str
    captures: list[Any]
    feedback_url: str
    frame_locator: Any
    step_label: str
    empty_route_labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class _RefundRouteOutcome:
    route: FeedbackRoute
    flow: _RefundFeedbackFlow
    result: FetchResult


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
        log_fn(logger, "登录态接近失效，先执行自动续期。")
        if renew_account_state_fn(account, logger=logger, profile_dir=profile_dir, headless=headless):
            return
        raise FetchError(
            "登录态续期失败，请重新保存登录态。",
            code=FetchErrorCode.SESSION_STATE_INVALID,
            evidence=[
                {
                    "kind": "session",
                    "label": "登录态续期",
                    "summary": "登录态接近失效且自动续期失败。",
                    "metadata": {"account_name": account.name},
                }
            ],
        )

    if validate_account_state_fn(account, logger=logger, profile_dir=profile_dir):
        return

    log_fn(logger, "登录态校验失败，尝试自动续期。")
    if renew_account_state_fn(account, logger=logger, profile_dir=profile_dir, headless=headless):
        return
    raise FetchError(
        "登录态无效，请重新保存登录态。",
        code=FetchErrorCode.SESSION_STATE_INVALID,
        evidence=[
            {
                "kind": "session",
                "label": "登录态校验",
                "summary": "登录态校验失败且自动续期失败。",
                "metadata": {"account_name": account.name},
            }
        ],
    )


def _collect_ios_refund_subject_captures(
    *,
    page: Any,
    captures: list[Any],
    logger: Logger | None,
    log_fn: LogFn,
    wait_or_cancel_fn: Callable[..., Any],
    fetch_paginated_refund_list_captures_fn: Callable[..., list[Any]] | None,
    is_cancelled: CancelCheck | None,
) -> list[Any]:
    return collect_ios_refund_subject_captures(
        page=page,
        captures=captures,
        logger=logger,
        log_fn=log_fn,
        wait_or_cancel_fn=wait_or_cancel_fn,
        fetch_paginated_refund_list_captures_fn=fetch_paginated_refund_list_captures_fn,
        is_cancelled=is_cancelled,
    )


def _recover_timeout_page_if_needed(
    page: Any,
    *,
    logger: Logger | None,
    log_fn: LogFn,
    safe_page_content_fn: Callable[..., str],
    is_cancelled: CancelCheck | None,
) -> bool:
    return recover_timeout_page_if_needed(
        page,
        logger=logger,
        log_fn=log_fn,
        safe_page_content_fn=safe_page_content_fn,
        is_cancelled=is_cancelled,
    )


def resolve_bootstrap_url_impl(account: AccountConfig, output_dir: Path) -> str:
    return account.home_url


def _collect_refund_feedback_flow(
    *,
    manifest: FetchRunManifest,
    page: Any,
    account: AccountConfig,
    output_dir: Path,
    captures: list[Any],
    logger: Logger | None,
    log_fn: LogFn,
    open_feedback_page_fn: Callable[..., str],
    build_feedback_url_fn: Callable[..., str],
    wait_for_iframe_ready_fn: Callable[..., Any],
    resolve_frame_locator_fn: Callable[..., Any],
    business_iframe_selector_fn: Callable[..., str],
    safe_page_content_fn: Callable[..., str],
    fetch_paginated_refund_list_captures_fn: Callable[..., list[Any]] | None,
    is_empty_refund_list_fn: Callable[..., bool],
    confirm_empty_refund_list_fn: Callable[..., tuple[bool, str]],
    is_cancelled: CancelCheck | None,
    step_label: str,
) -> _RefundFeedbackFlow:
    feedback_capture_start = len(captures)
    with fetch_step(manifest, f"打开{step_label}"):
        feedback_url = open_feedback_page_fn(
            page,
            account=account,
            logger=logger,
            build_feedback_url_fn=build_feedback_url_fn,
            wait_for_iframe_ready_fn=wait_for_iframe_ready_fn,
            is_cancelled=is_cancelled,
        )
    current_captures = captures[feedback_capture_start:]
    with fetch_step(manifest, f"定位{step_label} iframe"):
        frame_locator = resolve_frame_locator_fn(
            page,
            output_dir=output_dir,
            business_iframe_selector_fn=business_iframe_selector_fn,
            safe_page_content_fn=safe_page_content_fn,
        )
        list_text = frame_locator.locator("body").text_content(timeout=15000) or ""

    if step_label == "iOS退款问询":
        with fetch_step(manifest, f"切换{step_label}主体并查询"):
            current_captures = _collect_ios_refund_subject_captures(
                page=page,
                captures=current_captures,
                logger=logger,
                log_fn=log_fn,
                wait_or_cancel_fn=wait_for_timeout,
                fetch_paginated_refund_list_captures_fn=fetch_paginated_refund_list_captures_fn,
                is_cancelled=is_cancelled,
            )
    elif callable(fetch_paginated_refund_list_captures_fn):
        with fetch_step(manifest, f"补抓{step_label}分页"):
            current_captures = fetch_paginated_refund_list_captures_fn(
                page=page,
                captures=current_captures,
                logger=logger,
                log_fn=log_fn,
            )
    list_text = frame_locator.locator("body").text_content(timeout=15000) or ""

    add_fetch_evidence(
        manifest,
        kind="network",
        label=f"{step_label}响应",
        summary=f"捕获 {len(current_captures)} 条目标响应",
        metadata={"capture_count": len(current_captures)},
    )

    with fetch_step(manifest, f"确认{step_label}列表状态"):
        empty_confirmed, confirmed_list_text = confirm_empty_refund_list_fn(
            page=page,
            frame_locator=frame_locator,
            initial_text=list_text,
            captures=current_captures,
            is_empty_refund_list_fn=is_empty_refund_list_fn,
            is_cancelled=is_cancelled,
        )

    return _RefundFeedbackFlow(
        empty_confirmed=empty_confirmed,
        confirmed_list_text=confirmed_list_text,
        captures=current_captures,
        feedback_url=feedback_url,
        frame_locator=frame_locator,
        step_label=step_label,
        empty_route_labels=(step_label,) if empty_confirmed else (),
    )


def _build_collection_routes(
    fetch_notifications_fn: Callable[..., dict[str, Any]] | None,
    fetch_transaction_complaints_fn: Callable[..., dict[str, Any]] | None,
) -> tuple[CollectionRoute, ...]:
    routes: list[CollectionRoute] = []
    if callable(fetch_notifications_fn):
        routes.append(CollectionRoute(name="通知中心", step_label="通知中心", collect_fn=fetch_notifications_fn))
    if callable(fetch_transaction_complaints_fn):
        routes.append(
            CollectionRoute(name="交易投诉", step_label="交易投诉", collect_fn=fetch_transaction_complaints_fn)
        )
    return tuple(routes)


def _build_feedback_routes(
    build_feedback_url_fn: Callable[..., str],
    build_ios_refund_feedback_url_fn: Callable[..., str] | None,
) -> tuple[FeedbackRoute, ...]:
    routes = [
        FeedbackRoute(
            name="退款反馈页",
            step_label="退款反馈页",
            build_feedback_url_fn=build_feedback_url_fn,
        )
    ]
    if callable(build_ios_refund_feedback_url_fn):
        routes.append(
            FeedbackRoute(
                name="iOS退款问询",
                step_label="iOS退款问询",
                build_feedback_url_fn=build_ios_refund_feedback_url_fn,
            )
        )
    return tuple(routes)


def _collect_collection_route(
    manifest: FetchRunManifest,
    route: CollectionRoute,
    *,
    page: Any,
    account: AccountConfig,
    logger: Logger | None,
    output_dir: Path,
    log_fn: LogFn,
    wait_for_url_contains_fn: Callable[..., Any],
    safe_page_content_fn: Callable[..., str],
    is_cancelled: CancelCheck | None,
) -> dict[str, Any]:
    with fetch_step(manifest, f"采集{route.step_label}"):
        return route.collect_fn(
            page,
            account=account,
            logger=logger,
            output_dir=output_dir,
            log_fn=log_fn,
            wait_for_url_contains_fn=wait_for_url_contains_fn,
            safe_page_content_fn=safe_page_content_fn,
            is_cancelled=is_cancelled,
        )


def _collect_feedback_route_flow(
    manifest: FetchRunManifest,
    route: FeedbackRoute,
    *,
    page: Any,
    account: AccountConfig,
    output_dir: Path,
    captures: list[Any],
    logger: Logger | None,
    log_fn: LogFn,
    open_feedback_page_fn: Callable[..., str],
    wait_for_iframe_ready_fn: Callable[..., Any],
    resolve_frame_locator_fn: Callable[..., Any],
    business_iframe_selector_fn: Callable[..., str],
    safe_page_content_fn: Callable[..., str],
    fetch_paginated_refund_list_captures_fn: Callable[..., list[Any]] | None,
    is_empty_refund_list_fn: Callable[..., bool],
    confirm_empty_refund_list_fn: Callable[..., tuple[bool, str]],
    is_cancelled: CancelCheck | None,
) -> _RefundFeedbackFlow:
    return _collect_refund_feedback_flow(
        manifest=manifest,
        page=page,
        account=account,
        output_dir=output_dir,
        captures=captures,
        logger=logger,
        log_fn=log_fn,
        open_feedback_page_fn=open_feedback_page_fn,
        build_feedback_url_fn=route.build_feedback_url_fn,
        wait_for_iframe_ready_fn=wait_for_iframe_ready_fn,
        resolve_frame_locator_fn=resolve_frame_locator_fn,
        business_iframe_selector_fn=business_iframe_selector_fn,
        safe_page_content_fn=safe_page_content_fn,
        fetch_paginated_refund_list_captures_fn=fetch_paginated_refund_list_captures_fn,
        is_empty_refund_list_fn=is_empty_refund_list_fn,
        confirm_empty_refund_list_fn=confirm_empty_refund_list_fn,
        is_cancelled=is_cancelled,
        step_label=route.step_label,
    )


def _build_refund_route_result(
    *,
    manifest: FetchRunManifest,
    pipeline_context: PipelineContext,
    page: Any,
    context: Any,
    account: AccountConfig,
    output_dir: Path,
    profile_dir: str,
    route: FeedbackRoute,
    flow: _RefundFeedbackFlow,
    logger: Logger | None,
    is_cancelled: CancelCheck | None,
) -> _RefundRouteOutcome:
    if flow.empty_confirmed:
        with fetch_step(manifest, f"生成{route.step_label}空列表采集结果"):
            result = pipeline_context.build_empty_refund_result_fn(
                page=page,
                context=context,
                account=account,
                output_dir=output_dir,
                frame_locator=flow.frame_locator,
                list_text=flow.confirmed_list_text,
                captures=flow.captures,
                feedback_url=flow.feedback_url,
                profile_dir=profile_dir,
                logger=logger,
                safe_page_content_fn=pipeline_context.safe_page_content_fn,
                extract_current_account_name_fn=pipeline_context.extract_current_account_name_fn,
                is_cancelled=is_cancelled,
            )
    else:
        with fetch_step(manifest, f"生成{route.step_label}详情页采集结果"):
            result = pipeline_context.build_detail_result_fn(
                page=page,
                context=context,
                account=account,
                output_dir=output_dir,
                frame_locator=flow.frame_locator,
                captures=flow.captures,
                feedback_url=flow.feedback_url,
                profile_dir=profile_dir,
                logger=logger,
                safe_page_content_fn=pipeline_context.safe_page_content_fn,
                extract_current_account_name_fn=pipeline_context.extract_current_account_name_fn,
            )
    return _RefundRouteOutcome(route=route, flow=flow, result=result)


def _build_pipeline_context(
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
    build_ios_refund_feedback_url_fn: Callable[..., str] | None,
    wait_for_iframe_ready_fn: Callable[..., Any],
    resolve_frame_locator_fn: Callable[..., Any],
    business_iframe_selector_fn: Callable[..., str],
    safe_page_content_fn: Callable[..., str],
    fetch_notifications_fn: Callable[..., dict[str, Any]] | None,
    fetch_transaction_complaints_fn: Callable[..., dict[str, Any]] | None,
    fetch_paginated_refund_list_captures_fn: Callable[..., list[Any]] | None,
    is_empty_refund_list_fn: Callable[..., bool],
    confirm_empty_refund_list_fn: Callable[..., tuple[bool, str]],
    build_empty_refund_result_fn: Callable[..., FetchResult],
    build_detail_result_fn: Callable[..., FetchResult],
) -> PipelineContext:
    return PipelineContext(
        account_output_dir_fn=account_output_dir_fn,
        register_response_capture_fn=register_response_capture_fn,
        capture_response_payload_fn=capture_response_payload_fn,
        resolve_bootstrap_url_fn=resolve_bootstrap_url_fn,
        wait_for_url_contains_fn=wait_for_url_contains_fn,
        extract_current_account_name_fn=extract_current_account_name_fn,
        should_switch_for_account_fn=should_switch_for_account_fn,
        switch_to_account_fn=switch_to_account_fn,
        log_fn=log_fn,
        open_feedback_page_fn=open_feedback_page_fn,
        build_feedback_url_fn=build_feedback_url_fn,
        build_ios_refund_feedback_url_fn=build_ios_refund_feedback_url_fn,
        wait_for_iframe_ready_fn=wait_for_iframe_ready_fn,
        resolve_frame_locator_fn=resolve_frame_locator_fn,
        business_iframe_selector_fn=business_iframe_selector_fn,
        safe_page_content_fn=safe_page_content_fn,
        fetch_paginated_refund_list_captures_fn=fetch_paginated_refund_list_captures_fn,
        is_empty_refund_list_fn=is_empty_refund_list_fn,
        confirm_empty_refund_list_fn=confirm_empty_refund_list_fn,
        build_empty_refund_result_fn=build_empty_refund_result_fn,
        build_detail_result_fn=build_detail_result_fn,
        collection_routes=_build_collection_routes(fetch_notifications_fn, fetch_transaction_complaints_fn),
        feedback_routes=_build_feedback_routes(build_feedback_url_fn, build_ios_refund_feedback_url_fn),
    )


def _collect_collection_outcomes(
    manifest: FetchRunManifest,
    pipeline_context: PipelineContext,
    *,
    page: Any,
    account: AccountConfig,
    output_dir: Path,
    logger: Logger | None,
    is_cancelled: CancelCheck | None,
) -> dict[str, dict[str, Any]]:
    outcomes: dict[str, dict[str, Any]] = {}
    for route in pipeline_context.collection_routes:
        outcomes[route.name] = _collect_collection_route(
            manifest,
            route,
            page=page,
            account=account,
            logger=logger,
            output_dir=output_dir,
            log_fn=pipeline_context.log_fn,
            wait_for_url_contains_fn=pipeline_context.wait_for_url_contains_fn,
            safe_page_content_fn=pipeline_context.safe_page_content_fn,
            is_cancelled=is_cancelled,
        )
    return outcomes


def _fetch_account_in_page_with_context(
    page: Any,
    context: Any,
    account: AccountConfig,
    logger: Logger | None,
    profile_dir: str,
    is_cancelled: CancelCheck | None,
    *,
    pipeline_context: PipelineContext,
) -> FetchResult:
    output_dir = pipeline_context.account_output_dir_fn(account.name)
    manifest = start_fetch_run(account, profile_dir=profile_dir, output_dir=str(output_dir))

    def cleanup_response_capture() -> None:
        return None

    captures: list[Any] = []
    notification_outcome = default_notification_outcome()
    transaction_complaint_outcome = default_transaction_complaint_outcome()
    try:
        with fetch_step(manifest, "注册响应监听"):
            captures, cleanup_response_capture = pipeline_context.register_response_capture_fn(
                page, pipeline_context.capture_response_payload_fn
            )

        bootstrap_url = pipeline_context.resolve_bootstrap_url_fn(account, output_dir)
        if not page_has_backend_session(page):
            with fetch_step(manifest, "进入微信后台", detail=bootstrap_url):
                page.goto(bootstrap_url, wait_until="domcontentloaded", timeout=60000)
                pipeline_context.wait_for_url_contains_fn(
                    page, ("token=", "/wxamp/index/index"), timeout_ms=4000, is_cancelled=is_cancelled
                )
                set_page_home_ready(page, bootstrap_url == account.home_url)

        with fetch_step(manifest, "检查并恢复登录超时页"):
            if is_login_timeout_page(page, safe_page_content_fn=pipeline_context.safe_page_content_fn):
                recovered = _recover_timeout_page_if_needed(
                    page,
                    logger=logger,
                    log_fn=pipeline_context.log_fn,
                    safe_page_content_fn=pipeline_context.safe_page_content_fn,
                    is_cancelled=is_cancelled,
                )
                if recovered:
                    pipeline_context.wait_for_url_contains_fn(
                        page, ("token=", "/wxamp/index/index"), timeout_ms=4000, is_cancelled=is_cancelled
                    )

        if "token=" not in page.url and bootstrap_url == account.home_url:
            raise FetchError(
                "当前登录态未自动跳入后台页，且没有可复用的历史反馈页地址，无法启动自动切换账号。",
                code=FetchErrorCode.MISSING_TOKEN,
                evidence=[
                    {
                        "kind": "page",
                        "label": "后台入口地址",
                        "summary": "进入后台后未发现 token，且没有历史反馈页地址可复用。",
                        "metadata": {"page_url": str(getattr(page, "url", "") or ""), "bootstrap_url": bootstrap_url},
                    }
                ],
            )

        with fetch_step(manifest, "确认当前账号"):
            current_account_name = page_current_account_name(page)
            if not current_account_name:
                current_account_name = pipeline_context.extract_current_account_name_fn(page)
                if current_account_name:
                    set_page_current_account_name(page, current_account_name)

        with fetch_step(manifest, "切换目标账号", detail=account.name):
            if pipeline_context.should_switch_for_account_fn(account, current_account_name):
                pipeline_context.switch_to_account_fn(page, account.name, account.home_url, logger)
                set_page_current_account_name(page, account.name)
            elif account.is_entry_account:
                pipeline_context.log_fn(logger, "入口账号使用当前共享会话，不执行切换账号。")
            else:
                pipeline_context.log_fn(logger, f"账号 {account.name} 已处于当前会话，跳过切换步骤。")

        collection_outcomes = _collect_collection_outcomes(
            manifest,
            pipeline_context,
            page=page,
            account=account,
            output_dir=output_dir,
            logger=logger,
            is_cancelled=is_cancelled,
        )
        notification_outcome = collection_outcomes.get("通知中心", default_notification_outcome())
        transaction_complaint_outcome = collection_outcomes.get("交易投诉", default_transaction_complaint_outcome())

        refund_outcomes: tuple[_RefundRouteOutcome, ...] = ()
        if not transaction_complaint_outcome.get("enabled"):
            collected_refund_outcomes: list[_RefundRouteOutcome] = []
            for route in pipeline_context.feedback_routes:
                flow = _collect_feedback_route_flow(
                    manifest=manifest,
                    route=route,
                    page=page,
                    account=account,
                    output_dir=output_dir,
                    captures=captures,
                    logger=logger,
                    log_fn=pipeline_context.log_fn,
                    open_feedback_page_fn=pipeline_context.open_feedback_page_fn,
                    wait_for_iframe_ready_fn=pipeline_context.wait_for_iframe_ready_fn,
                    resolve_frame_locator_fn=pipeline_context.resolve_frame_locator_fn,
                    business_iframe_selector_fn=pipeline_context.business_iframe_selector_fn,
                    safe_page_content_fn=pipeline_context.safe_page_content_fn,
                    fetch_paginated_refund_list_captures_fn=pipeline_context.fetch_paginated_refund_list_captures_fn,
                    is_empty_refund_list_fn=pipeline_context.is_empty_refund_list_fn,
                    confirm_empty_refund_list_fn=pipeline_context.confirm_empty_refund_list_fn,
                    is_cancelled=is_cancelled,
                )
                collected_refund_outcomes.append(
                    _build_refund_route_result(
                        manifest=manifest,
                        pipeline_context=pipeline_context,
                        page=page,
                        context=context,
                        account=account,
                        output_dir=output_dir,
                        profile_dir=profile_dir,
                        route=route,
                        flow=flow,
                        logger=logger,
                        is_cancelled=is_cancelled,
                    )
                )
            refund_outcomes = tuple(collected_refund_outcomes)

        result, result_extra = compose_fetch_result(
            page=page,
            account_name=account.name,
            refund_outcomes=refund_outcomes,
            notification_outcome=notification_outcome,
            transaction_complaint_outcome=transaction_complaint_outcome,
            set_page_current_account_name_fn=set_page_current_account_name,
        )
        write_fetch_result_payload(
            account.name,
            result,
            result_extra=result_extra,
            notification_outcome=notification_outcome,
        )
        if result.ok:
            log_fetch_success_summary(
                account_name=account.name,
                logger=logger,
                log_fn=pipeline_context.log_fn,
                notification_outcome=notification_outcome,
                transaction_complaint_outcome=transaction_complaint_outcome,
                refund_outcomes=refund_outcomes,
            )
        set_page_home_ready(page, False)
        persist_fetch_run(manifest, account_name=account.name, result=result)
        return cast(FetchResult, result)
    except Exception as exc:
        persist_fetch_run(manifest, account_name=account.name, error=exc)
        raise
    finally:
        cleanup_response_capture()


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
    fetch_transaction_complaints_fn: Callable[..., dict[str, Any]] | None = None,
    fetch_paginated_refund_list_captures_fn: Callable[..., list[Any]] | None = None,
    is_empty_refund_list_fn: Callable[..., bool],
    confirm_empty_refund_list_fn: Callable[..., tuple[bool, str]],
    build_empty_refund_result_fn: Callable[..., FetchResult],
    build_detail_result_fn: Callable[..., FetchResult],
    build_ios_refund_feedback_url_fn: Callable[..., str] | None = None,
) -> FetchResult:
    pipeline_context = _build_pipeline_context(
        account_output_dir_fn=account_output_dir_fn,
        register_response_capture_fn=register_response_capture_fn,
        capture_response_payload_fn=capture_response_payload_fn,
        resolve_bootstrap_url_fn=resolve_bootstrap_url_fn,
        wait_for_url_contains_fn=wait_for_url_contains_fn,
        extract_current_account_name_fn=extract_current_account_name_fn,
        should_switch_for_account_fn=should_switch_for_account_fn,
        switch_to_account_fn=switch_to_account_fn,
        log_fn=log_fn,
        open_feedback_page_fn=open_feedback_page_fn,
        build_feedback_url_fn=build_feedback_url_fn,
        build_ios_refund_feedback_url_fn=build_ios_refund_feedback_url_fn,
        wait_for_iframe_ready_fn=wait_for_iframe_ready_fn,
        resolve_frame_locator_fn=resolve_frame_locator_fn,
        business_iframe_selector_fn=business_iframe_selector_fn,
        safe_page_content_fn=safe_page_content_fn,
        fetch_notifications_fn=fetch_notifications_fn,
        fetch_transaction_complaints_fn=fetch_transaction_complaints_fn,
        fetch_paginated_refund_list_captures_fn=fetch_paginated_refund_list_captures_fn,
        is_empty_refund_list_fn=is_empty_refund_list_fn,
        confirm_empty_refund_list_fn=confirm_empty_refund_list_fn,
        build_empty_refund_result_fn=build_empty_refund_result_fn,
        build_detail_result_fn=build_detail_result_fn,
    )
    return _fetch_account_in_page_with_context(
        page,
        context,
        account,
        logger,
        profile_dir,
        is_cancelled,
        pipeline_context=pipeline_context,
    )


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
    return run_fetch_accounts_batch(
        accounts,
        headless=headless,
        logger=logger,
        progress=progress,
        profile_dir=profile_dir,
        is_cancelled=is_cancelled,
        sync_playwright_fn=sync_playwright_fn,
        path_exists_fn=path_exists_fn,
        validate_shared_browser_profile_dir_fn=validate_shared_browser_profile_dir_fn,
        create_browser_context_fn=create_browser_context_fn,
        prepare_account_session_fn=lambda account, logger, profile_dir, headless: _prepare_account_session_for_fetch(
            account,
            logger=logger,
            profile_dir=profile_dir,
            headless=headless,
            log_fn=lambda current_logger, message: current_logger(message) if current_logger else None,
            validate_account_state_fn=validate_account_state_fn,
            renew_account_state_fn=renew_account_state_fn,
        ),
        fetch_account_in_page_fn=fetch_account_in_page_fn,
        acquire_group_runtime_fn=acquire_group_runtime_fn,
        invalidate_group_runtime_fn=invalidate_group_runtime_fn,
        update_runtime_current_account_name_fn=update_runtime_current_account_name_fn,
        should_invalidate_runtime_fn=should_invalidate_runtime_fn,
        write_batch_diagnostic_index_safely_fn=write_batch_diagnostic_index_safely,
        batch_runtime_refresh_every=batch_runtime_refresh_every,
    )
