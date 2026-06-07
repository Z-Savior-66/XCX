from __future__ import annotations

from collections.abc import Callable
from typing import Any

from desktop_py.core.fetcher_common import CancelCheck, FetchError, Logger
from desktop_py.core.fetcher_support import recover_login_timeout_page

LogFn = Callable[[Logger | None, str], None]


def page_current_account_name(page: Any) -> str:
    try:
        return str(getattr(page, "_current_account_name_cache", "") or "").strip()
    except Exception:
        return ""


def set_page_current_account_name(page: Any, account_name: str) -> None:
    try:
        setattr(page, "_current_account_name_cache", account_name.strip())
    except Exception:
        pass


def page_has_backend_session(page: Any) -> bool:
    try:
        current_url = str(getattr(page, "url", "") or "")
    except Exception:
        return False
    return any(keyword in current_url for keyword in ("token=", "/wxamp/index/index", "pluginRedirect/gameFeedback"))


def wait_for_timeout(current_page: Any, wait_ms: int, _cancelled: CancelCheck | None = None) -> None:
    current_page.wait_for_timeout(wait_ms)


def _find_business_frame(page: Any) -> Any | None:
    try:
        frames = list(getattr(page, "frames", []) or [])
    except Exception:
        return None
    for frame in frames:
        try:
            if str(getattr(frame, "name", "") or "").strip() == "js_iframe":
                return frame
            frame_url = str(getattr(frame, "url", "") or "")
        except Exception:
            continue
        if "gamemp.weixin.qq.com/minigame/index.html" in frame_url:
            return frame
    return None


def _click_first_visible_button(frame: Any) -> bool:
    try:
        buttons = frame.locator("button")
        button_count = int(buttons.count())
    except Exception:
        return False
    for index in range(button_count):
        button = buttons.nth(index)
        try:
            is_visible = bool(
                button.evaluate(
                    """
                    (element) => {
                        const style = window.getComputedStyle(element);
                        const text = (element.innerText || "").trim();
                        return (
                            style.display !== "none"
                            && style.visibility !== "hidden"
                            && element.offsetParent !== null
                            && text.length > 0
                        );
                    }
                    """
                )
            )
        except Exception:
            continue
        if not is_visible:
            continue
        button.click(timeout=10000)
        return True
    return False


def collect_ios_refund_subject_captures(
    *,
    page: Any,
    captures: list[Any],
    logger: Logger | None,
    log_fn: LogFn,
    wait_or_cancel_fn: Callable[..., Any],
    fetch_paginated_refund_list_captures_fn: Callable[..., list[Any]] | None,
    is_cancelled: CancelCheck | None,
) -> list[Any]:
    frame = _find_business_frame(page)
    if frame is None:
        log_fn(logger, "iOS退款问询未定位到业务 Frame，跳过主体切换。")
        return captures

    try:
        frame.wait_for_selector(".drop-selected", timeout=10000)
    except Exception:
        return captures

    working_captures = list(captures)
    if callable(fetch_paginated_refund_list_captures_fn):
        working_captures = fetch_paginated_refund_list_captures_fn(
            page=page,
            captures=working_captures,
            logger=logger,
            log_fn=log_fn,
        )

    try:
        subject_options = frame.eval_on_selector_all(
            ".dropdown-switch-item",
            """(elements) => elements.map((element) => ({
                title: (element.getAttribute("title") || "").trim(),
                text: (element.textContent || "").trim(),
            }))""",
        )
        current_subject = str(frame.eval_on_selector(".drop-selected", "element => element.value || ''") or "").strip()
    except Exception:
        return working_captures

    if len(subject_options) <= 1:
        return working_captures

    expect_response = getattr(page, "expect_response", None)
    for index, option in enumerate(subject_options):
        title = str(option.get("title") or option.get("text") or "").strip()
        if not title or title == current_subject:
            continue
        action_started = False

        def trigger_search() -> None:
            nonlocal action_started
            action_started = True
            frame.locator(".dropdown_switch").click(timeout=10000)
            frame.wait_for_timeout(300)
            frame.locator(".dropdown_data_item").nth(index).click(timeout=10000)
            frame.wait_for_timeout(300)
            if not _click_first_visible_button(frame):
                raise FetchError("iOS退款问询页面未找到可点击的搜索按钮。")

        if callable(expect_response):
            try:
                with expect_response(
                    lambda response: "getiaprefundlist" in str(getattr(response, "url", "") or "").lower(),
                    timeout=10000,
                ):
                    trigger_search()
            except Exception:
                if not action_started:
                    trigger_search()
        else:
            trigger_search()

        wait_or_cancel_fn(page, 1200, is_cancelled)
        working_captures = list(captures)
        if callable(fetch_paginated_refund_list_captures_fn):
            working_captures = fetch_paginated_refund_list_captures_fn(
                page=page,
                captures=working_captures,
                logger=logger,
                log_fn=log_fn,
            )
        current_subject = title

    return working_captures


def recover_timeout_page_if_needed(
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
        wait_or_cancel_fn=wait_for_timeout,
        is_cancelled=is_cancelled,
    )


def set_page_home_ready(page: Any, ready: bool) -> None:
    try:
        setattr(page, "_home_ready_cache", bool(ready))
    except Exception:
        pass


def page_home_ready(page: Any) -> bool:
    try:
        return bool(getattr(page, "_home_ready_cache", False))
    except Exception:
        return False
