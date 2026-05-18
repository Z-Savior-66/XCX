from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from desktop_py.core.fetcher_routes import CollectionRoute, FeedbackRoute
from desktop_py.core.models import AccountConfig, FetchResult


@dataclass(frozen=True)
class PipelineContext:
    account_output_dir_fn: Callable[[str], Path]
    register_response_capture_fn: Callable[..., tuple[list[Any], Callable[[], None]]]
    capture_response_payload_fn: Callable[..., Any]
    resolve_bootstrap_url_fn: Callable[[AccountConfig, Path], str]
    wait_for_url_contains_fn: Callable[..., Any]
    extract_current_account_name_fn: Callable[[Any], str]
    should_switch_for_account_fn: Callable[[AccountConfig, str], bool]
    switch_to_account_fn: Callable[..., Any]
    log_fn: Callable[[Callable[[str], None] | None, str], None]
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
    build_empty_refund_result_fn: Callable[..., FetchResult]
    build_detail_result_fn: Callable[..., FetchResult]
    collection_routes: tuple[CollectionRoute, ...]
    feedback_route: FeedbackRoute
