from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from desktop_py.core.fetcher_routes import CollectionRoute, FeedbackRoute
from desktop_py.core.models import AccountConfig, FetchResult


@dataclass(frozen=True)
class FetcherDeps:
    """Groups all dependency injection callbacks for fetcher pipeline functions."""

    sync_playwright_fn: Callable[..., Any]
    path_exists_fn: Callable[[Path], bool]
    validate_shared_browser_profile_dir_fn: Callable[[str], str]
    create_browser_context_fn: Callable[..., tuple[Any | None, Any]]
    validate_account_state_fn: Callable[..., bool]
    renew_account_state_fn: Callable[..., bool]
    fetch_account_in_page_fn: Callable[..., FetchResult]
    acquire_group_runtime_fn: Callable[..., Any]
    release_group_runtime_fn: Callable[[Any], None]
    invalidate_group_runtime_fn: Callable[..., None]
    runtime_current_account_name_fn: Callable[[Any], str]
    update_runtime_current_account_name_fn: Callable[[Any, str], None]
    should_invalidate_runtime_fn: Callable[[Exception], bool]


@dataclass(frozen=True)
class NavigationContext:
    """Page navigation, account switching, and session management."""

    account_output_dir_fn: Callable[[str], Path]
    resolve_bootstrap_url_fn: Callable[[AccountConfig, Path], str]
    wait_for_url_contains_fn: Callable[..., Any]
    extract_current_account_name_fn: Callable[[Any], str]
    should_switch_for_account_fn: Callable[[AccountConfig, str], bool]
    switch_to_account_fn: Callable[..., Any]


@dataclass(frozen=True)
class CaptureContext:
    """Feedback page interaction, iframe handling, and data capture."""

    register_response_capture_fn: Callable[..., tuple[list[Any], Callable[[], None]]]
    capture_response_payload_fn: Callable[..., Any]
    open_feedback_page_fn: Callable[..., str]
    build_feedback_url_fn: Callable[..., str]
    build_ios_refund_feedback_url_fn: Callable[..., str] | None
    wait_for_iframe_ready_fn: Callable[..., Any]
    resolve_frame_locator_fn: Callable[..., Any]
    business_iframe_selector_fn: Callable[..., str]
    safe_page_content_fn: Callable[..., str]
    fetch_paginated_refund_list_captures_fn: Callable[..., list[Any]] | None
    is_empty_refund_list_fn: Callable[..., bool]
    confirm_empty_refund_list_fn: Callable[..., tuple[bool, str]]


@dataclass(frozen=True)
class ResultBuildContext:
    """Result construction callbacks."""

    build_empty_refund_result_fn: Callable[..., FetchResult]
    build_detail_result_fn: Callable[..., FetchResult]


@dataclass(frozen=True)
class SharedContext:
    """Common utilities, logging, and routing configuration."""

    log_fn: Callable[[Callable[[str], None] | None, str], None]
    collection_routes: tuple[CollectionRoute, ...]
    feedback_routes: tuple[FeedbackRoute, ...]


@dataclass(frozen=True)
class PipelineContext:
    """Aggregates all pipeline sub-contexts."""

    navigation: NavigationContext
    capture: CaptureContext
    result: ResultBuildContext
    shared: SharedContext
