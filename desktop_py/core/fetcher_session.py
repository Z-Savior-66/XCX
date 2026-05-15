from __future__ import annotations

import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from desktop_py.core.diagnostic_log import log_session_offline, log_session_renew_failed
from desktop_py.core.fetcher_support import (
    FetchError,
    ensure_account_session_available,
    normalize_profile_dir,
    persist_storage_state,
)
from desktop_py.core.models import (
    SESSION_STATUS_EXPIRED,
    SESSION_STATUS_VALID,
    AccountConfig,
)
from desktop_py.core.session_links import canonical_feedback_url, refresh_account_feedback_url
from desktop_py.core.session_probe import (
    SessionVerification,
    _has_backend_session,
    _now_text,
    _probe_account_session_result,
    _wait_for_backend_session,
    apply_session_verification,
    mark_account_session_missing,
    session_source_for_profile_dir,
    verify_backend_session,
)

Logger = Callable[[str], None]
CancelCheck = Callable[[], bool]
LogFn = Callable[[Logger | None, str], None]


def _create_state_file_context(
    playwright: Any,
    account: AccountConfig,
    headless: bool,
    _profile_dir: str,
) -> tuple[Any, Any]:
    browser = playwright.chromium.launch(headless=headless)
    try:
        context = browser.new_context(storage_state=str(account.state_path), viewport={"width": 1440, "height": 1200})
    except Exception:
        browser.close()
        raise
    return browser, context


def _wait_for_login_success(
    account: AccountConfig,
    page: Any,
    context: Any,
    state_path: Path,
    *,
    wait_seconds: int,
    datetime_cls: type[datetime],
    is_cancelled: CancelCheck | None,
    wait_or_cancel_fn: Callable[..., Any],
    logger: Logger | None = None,
    log_fn: LogFn | None = None,
    sync_playwright_fn: Callable[..., Any] | None = None,
    create_browser_context_fn: Callable[..., tuple[Any | None, Any]] | None = None,
    close_page_fn: Callable[[Any], None] | None = None,
    close_context_and_browser_fn: Callable[..., None] | None = None,
    headless_verify: bool = True,
    profile_dir: str = "",
) -> None:
    def fallback_verify(temp_state_path: str) -> bool:
        if sync_playwright_fn is None or create_browser_context_fn is None:
            return False
        temp_account = AccountConfig(
            name=account.name,
            state_path=temp_state_path,
            is_entry_account=account.is_entry_account,
            feedback_url="",
            home_url=account.home_url,
            enabled=account.enabled,
        )
        with sync_playwright_fn() as verify_playwright:
            verify_browser, verify_context = create_browser_context_fn(
                verify_playwright, temp_account, headless_verify, ""
            )
            verify_page = verify_context.new_page()
            try:
                result = _probe_account_session_result(
                    verify_page,
                    temp_account,
                    logger=logger,
                    log_fn=log_fn,
                    wait_for_url_contains_fn=lambda current_page, keywords, timeout_ms=10000, is_cancelled=None: (
                        _wait_for_backend_session(
                            current_page,
                            wait_for_url_contains_fn=lambda page_obj, url_keywords, timeout_ms=timeout_ms: any(
                                keyword in str(getattr(page_obj, "url", "") or "") for keyword in url_keywords
                            ),
                            timeout_ms=timeout_ms,
                        )
                    ),
                    timeout_ms=10000,
                )
                return result.valid
            finally:
                if callable(close_page_fn):
                    close_page_fn(verify_page)
                if callable(close_context_and_browser_fn):
                    close_context_and_browser_fn(
                        verify_context,
                        verify_browser,
                        state_path=None,
                        persist_state=False,
                    )
                else:
                    verify_context.close()
                    if verify_browser:
                        verify_browser.close()

    deadline = datetime_cls.now().timestamp() + wait_seconds
    while datetime_cls.now().timestamp() < deadline:
        wait_or_cancel_fn(page, 2000, is_cancelled)
        if _has_backend_session(page):
            refresh_account_feedback_url(account, str(getattr(page, "url", "") or ""))
            persist_storage_state(
                context,
                str(state_path),
                page=page,
                logger=logger,
                log_fn=log_fn,
                wait_or_cancel_fn=wait_or_cancel_fn,
                is_cancelled=is_cancelled,
                fallback_verify_fn=fallback_verify if sync_playwright_fn and create_browser_context_fn else None,
            )
            apply_session_verification(
                account,
                SessionVerification(
                    True,
                    status=SESSION_STATUS_VALID,
                    actual_account_name=verify_backend_session(page, account).actual_account_name,
                    feedback_url=canonical_feedback_url(str(getattr(page, "url", "") or "")),
                    reason="登录成功并已保存登录态",
                    session_source=session_source_for_profile_dir(profile_dir),
                ),
                profile_dir=profile_dir,
                renewed=True,
            )
            return
    raise FetchError("未在限定时间内检测到登录成功，已保留原登录态文件。")


def save_login_state_impl(
    account: AccountConfig,
    wait_seconds: int,
    logger: Logger | None = None,
    is_cancelled: CancelCheck | None = None,
    *,
    sync_playwright_fn: Callable[..., Any],
    datetime_cls: type[datetime],
    log_fn: LogFn,
    wait_or_cancel_fn: Callable[..., Any],
    close_page_fn: Callable[[Any], None],
    close_context_and_browser_fn: Callable[..., None],
) -> str:
    state_path = Path(account.state_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright_fn() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1440, "height": 1200})
        page = context.new_page()
        try:
            page.goto(account.home_url, wait_until="domcontentloaded")
            log_fn(logger, f"已打开微信后台登录页，请在 {wait_seconds} 秒内完成账号 {account.name} 的扫码登录。")
            log_fn(logger, "如果页面已经是登录后的后台首页，无需重复扫码，保持页面打开等待程序自动保存即可。")

            try:
                _wait_for_login_success(
                    account,
                    page,
                    context,
                    state_path,
                    wait_seconds=wait_seconds,
                    datetime_cls=datetime_cls,
                    is_cancelled=is_cancelled,
                    wait_or_cancel_fn=wait_or_cancel_fn,
                    logger=logger,
                    log_fn=log_fn,
                    sync_playwright_fn=sync_playwright_fn,
                    create_browser_context_fn=_create_state_file_context,
                    close_page_fn=close_page_fn,
                    close_context_and_browser_fn=close_context_and_browser_fn,
                    profile_dir="",
                )
            except FetchError as exc:
                raise FetchError(f"账号 {account.name} {exc}") from exc
        finally:
            close_page_fn(page)
            close_context_and_browser_fn(context, browser)

    account.last_login_at = _now_text()
    log_fn(logger, f"登录态已保存到 {state_path}")
    return str(state_path)


def save_login_state_with_profile_impl(
    account: AccountConfig,
    wait_seconds: int,
    profile_dir: str,
    logger: Logger | None = None,
    is_cancelled: CancelCheck | None = None,
    *,
    sync_playwright_fn: Callable[..., Any],
    datetime_cls: type[datetime],
    validate_shared_browser_profile_dir_fn: Callable[[str], str],
    log_fn: LogFn,
    wait_or_cancel_fn: Callable[..., Any],
    close_page_fn: Callable[[Any], None],
    close_context_and_browser_fn: Callable[..., None],
) -> str:
    user_data_dir = Path(
        normalize_profile_dir(
            profile_dir, validate_shared_browser_profile_dir_fn=validate_shared_browser_profile_dir_fn
        )
    )
    user_data_dir.mkdir(parents=True, exist_ok=True)
    state_path = Path(account.state_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright_fn() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=False,
            viewport={"width": 1440, "height": 1200},
        )
        page = context.new_page()
        try:
            page.goto(account.home_url, wait_until="domcontentloaded")
            log_fn(logger, f"已打开共享浏览器资料目录，请在 {wait_seconds} 秒内完成账号 {account.name} 的扫码登录。")
            log_fn(logger, "如果共享资料目录里已经保留有效登录态，无需重复扫码，保持页面打开等待程序自动保存即可。")

            try:
                _wait_for_login_success(
                    account,
                    page,
                    context,
                    state_path,
                    wait_seconds=wait_seconds,
                    datetime_cls=datetime_cls,
                    is_cancelled=is_cancelled,
                    wait_or_cancel_fn=wait_or_cancel_fn,
                    logger=logger,
                    log_fn=log_fn,
                    sync_playwright_fn=sync_playwright_fn,
                    create_browser_context_fn=_create_state_file_context,
                    close_page_fn=close_page_fn,
                    close_context_and_browser_fn=close_context_and_browser_fn,
                    profile_dir=str(user_data_dir),
                )
            except FetchError as exc:
                raise FetchError(f"账号 {account.name} {exc}") from exc
        finally:
            close_page_fn(page)
            close_context_and_browser_fn(context, None)

    account.last_login_at = _now_text()
    log_fn(logger, f"共享资料目录登录态已同步保存到 {state_path}")
    return str(state_path)


def validate_account_state_impl(
    account: AccountConfig,
    logger: Logger | None = None,
    profile_dir: str = "",
    *,
    sync_playwright_fn: Callable[..., Any],
    path_exists_fn: Callable[..., bool],
    validate_shared_browser_profile_dir_fn: Callable[[str], str],
    create_browser_context_fn: Callable[..., tuple[Any | None, Any]],
    wait_for_url_contains_fn: Callable[..., Any],
    close_page_fn: Callable[[Any], None],
    close_context_and_browser_fn: Callable[..., None],
    log_fn: LogFn,
) -> bool:
    normalized_profile_dir = normalize_profile_dir(
        profile_dir,
        validate_shared_browser_profile_dir_fn=validate_shared_browser_profile_dir_fn,
    )
    state_path = ensure_account_session_available(
        account,
        normalized_profile_dir,
        path_exists_fn=path_exists_fn,
        error_cls=None,
    )
    if state_path is None:
        mark_account_session_missing(account, profile_dir=normalized_profile_dir, reason="缺少可用登录态")
        return False

    with sync_playwright_fn() as playwright:
        browser, context = create_browser_context_fn(playwright, account, True, normalized_profile_dir)
        page = context.new_page()
        try:
            verification = _probe_account_session_result(
                page,
                account,
                logger=logger,
                log_fn=log_fn,
                wait_for_url_contains_fn=wait_for_url_contains_fn,
                timeout_ms=10000,
            )
            valid = verification.valid
        except PlaywrightTimeoutError:
            valid = False
            verification = SessionVerification(
                False,
                status=SESSION_STATUS_EXPIRED,
                reason="等待后台页面超时",
                branch="backend_page_timeout",
                page_url=str(getattr(page, "url", "") or ""),
                should_retry=True,
            )
        finally:
            close_page_fn(page)
            close_context_and_browser_fn(
                context,
                browser,
                state_path=None,
                persist_state=False,
            )

    verification = SessionVerification(
        verification.valid,
        status=verification.status if valid else verification.status,
        actual_account_name=verification.actual_account_name,
        feedback_url=verification.feedback_url,
        reason=verification.reason,
        branch=verification.branch,
        page_url=verification.page_url,
        should_retry=verification.should_retry,
        should_relogin=verification.should_relogin,
        session_source=session_source_for_profile_dir(normalized_profile_dir),
    )
    apply_session_verification(account, verification, profile_dir=normalized_profile_dir)
    reason = f"：{verification.reason}" if not valid and verification.reason else ""
    log_fn(logger, f"账号 {account.name} 登录态校验结果：{'有效' if valid else '无效'}{reason}")
    if not valid:
        log_session_offline(
            account.name,
            verification.reason or "未识别到可用后台登录态",
            branch=verification.branch,
            page_url=verification.page_url,
        )
    return valid


def _renew_temp_state_path(state_path: Path) -> Path:
    return state_path.with_name(f".{state_path.name}.renew.tmp")


def _backup_state_path(state_path: Path) -> Path:
    return state_path.with_name(f"{state_path.name}.bak")


def _replace_state_with_verified_temp(temp_state_path: Path, state_path: Path) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    if state_path.exists():
        shutil.copy2(state_path, _backup_state_path(state_path))
    temp_state_path.replace(state_path)


def _unique_switch_account_names(names: list[str] | None) -> list[str]:
    unique_names: list[str] = []
    for name in names or []:
        normalized_name = str(name).strip()
        if normalized_name and normalized_name not in unique_names:
            unique_names.append(normalized_name)
    return unique_names


def _select_renew_switch_account_name(
    names: list[str] | None,
    *,
    current_account_name: str = "",
    previous_account_name: str = "",
) -> str:
    unique_names = _unique_switch_account_names(names)
    current_name = current_account_name.strip()
    previous_name = previous_account_name.strip()
    reference_name = ""
    if current_name in unique_names:
        reference_name = current_name
    elif previous_name in unique_names:
        reference_name = previous_name
    if reference_name:
        start_index = unique_names.index(reference_name) + 1
        for offset in range(len(unique_names)):
            name = unique_names[(start_index + offset) % len(unique_names)]
            if name != current_name:
                return name
        return ""
    for name in unique_names:
        if name != current_name and name != previous_name:
            return name
    for name in unique_names:
        if name != current_name:
            return name
    return ""


def _visible_switch_account_names_from_error(error_message: str) -> list[str]:
    marker = "当前可见账号："
    if marker not in error_message:
        return []
    names_text = error_message.split(marker, 1)[1].strip().rstrip("。.")
    return _unique_switch_account_names(names_text.split("、"))


def _switch_to_renew_account(
    page: Any,
    switch_account_name: str,
    *,
    account: AccountConfig,
    logger: Logger | None,
    log_fn: LogFn,
    switch_to_account_fn: Callable[..., Any],
    current_account_name: str = "",
    previous_account_name: str = "",
) -> None:
    log_fn(logger, f"自动续期准备切换到轮换账号：{switch_account_name}。")
    try:
        switch_to_account_fn(page, switch_account_name, account.home_url, logger)
        return
    except Exception as exc:
        visible_names = _visible_switch_account_names_from_error(str(exc))
        retry_account_name = _select_renew_switch_account_name(
            visible_names,
            current_account_name=current_account_name,
            previous_account_name=previous_account_name,
        )
        if not retry_account_name or retry_account_name == switch_account_name:
            raise FetchError(f"自动续期轮换切换失败：{exc}") from exc

    log_fn(logger, f"自动续期轮换账号不可见，改为切换到当前可见账号：{retry_account_name}。")
    try:
        switch_to_account_fn(page, retry_account_name, account.home_url, logger)
    except Exception as exc:
        raise FetchError(f"自动续期轮换切换失败：{exc}") from exc


def _verify_saved_state_file(
    playwright: Any,
    account: AccountConfig,
    state_path: Path,
    *,
    headless: bool,
    create_browser_context_fn: Callable[..., tuple[Any | None, Any]],
    wait_for_url_contains_fn: Callable[..., Any],
    close_page_fn: Callable[[Any], None],
    close_context_and_browser_fn: Callable[..., None],
) -> SessionVerification:
    verify_account = AccountConfig(
        name=account.name,
        state_path=str(state_path),
        is_entry_account=account.is_entry_account,
        feedback_url="",
        home_url=account.home_url,
        enabled=account.enabled,
    )
    verify_browser, verify_context = create_browser_context_fn(playwright, verify_account, headless, "")
    verify_page = verify_context.new_page()
    try:
        return _probe_account_session_result(
            verify_page,
            verify_account,
            wait_for_url_contains_fn=wait_for_url_contains_fn,
            timeout_ms=10000,
        )
    except PlaywrightTimeoutError:
        return SessionVerification(
            False,
            status=SESSION_STATUS_EXPIRED,
            reason="保存后复验等待后台页面超时",
            branch="saved_state_verify_timeout",
            page_url=str(getattr(verify_page, "url", "") or ""),
            should_retry=True,
        )
    finally:
        close_page_fn(verify_page)
        close_context_and_browser_fn(
            verify_context,
            verify_browser,
            state_path=None,
            persist_state=False,
        )


def renew_account_state_impl(
    account: AccountConfig,
    logger: Logger | None = None,
    profile_dir: str = "",
    headless: bool = True,
    *,
    sync_playwright_fn: Callable[..., Any],
    path_exists_fn: Callable[..., bool],
    validate_shared_browser_profile_dir_fn: Callable[[str], str],
    create_browser_context_fn: Callable[..., tuple[Any | None, Any]],
    wait_for_url_contains_fn: Callable[..., Any],
    wait_or_cancel_fn: Callable[..., Any],
    close_page_fn: Callable[[Any], None],
    close_context_and_browser_fn: Callable[..., None],
    log_fn: LogFn,
    renew_switch_account_names: list[str] | None = None,
    switch_to_account_fn: Callable[..., Any] | None = None,
) -> bool:
    log_fn(logger, f"开始自动续期账号 {account.name}。")
    normalized_profile_dir = normalize_profile_dir(
        profile_dir,
        validate_shared_browser_profile_dir_fn=validate_shared_browser_profile_dir_fn,
    )
    state_path = ensure_account_session_available(
        account,
        normalized_profile_dir,
        path_exists_fn=path_exists_fn,
        error_cls=None,
    )
    if state_path is None:
        mark_account_session_missing(account, profile_dir=normalized_profile_dir, reason="缺少可用登录态")
        log_fn(logger, f"账号 {account.name} 自动续期失败：缺少可用登录态。")
        return False

    with sync_playwright_fn() as playwright:
        browser, context = create_browser_context_fn(playwright, account, headless, normalized_profile_dir)
        page = context.new_page()
        renewed = False
        temp_state_path = _renew_temp_state_path(Path(state_path))
        try:
            verification = _probe_account_session_result(
                page,
                account,
                logger=logger,
                log_fn=log_fn,
                wait_for_url_contains_fn=wait_for_url_contains_fn,
                timeout_ms=10000,
            )
            if verification.valid:
                try:
                    switch_account_name = _select_renew_switch_account_name(
                        renew_switch_account_names,
                        current_account_name=verification.actual_account_name,
                        previous_account_name=account.last_actual_account_name,
                    )
                    if switch_account_name and callable(switch_to_account_fn):
                        _switch_to_renew_account(
                            page,
                            switch_account_name,
                            account=account,
                            logger=logger,
                            log_fn=log_fn,
                            switch_to_account_fn=switch_to_account_fn,
                            current_account_name=verification.actual_account_name,
                            previous_account_name=account.last_actual_account_name,
                        )
                    persist_storage_state(
                        context,
                        str(temp_state_path),
                        page=page,
                        logger=logger,
                        log_fn=log_fn,
                        wait_or_cancel_fn=wait_or_cancel_fn,
                    )
                    verification = _verify_saved_state_file(
                        playwright,
                        account,
                        temp_state_path,
                        headless=headless,
                        create_browser_context_fn=create_browser_context_fn,
                        wait_for_url_contains_fn=wait_for_url_contains_fn,
                        close_page_fn=close_page_fn,
                        close_context_and_browser_fn=close_context_and_browser_fn,
                    )
                    renewed = verification.valid
                    if renewed:
                        _replace_state_with_verified_temp(temp_state_path, Path(state_path))
                        log_fn(logger, "续期登录态已通过保存后复验并替换正式文件。")
                    else:
                        verification = SessionVerification(
                            False,
                            status=verification.status,
                            actual_account_name=verification.actual_account_name,
                            feedback_url=verification.feedback_url,
                            reason=f"保存后复验失败：{verification.reason}",
                            branch=verification.branch,
                            page_url=verification.page_url,
                            should_retry=verification.should_retry,
                            should_relogin=verification.should_relogin,
                        )
                except Exception as exc:
                    renewed = False
                    reason = str(exc)
                    if not reason.startswith("自动续期轮换切换失败"):
                        reason = f"保存续期登录态失败：{exc}"
                    verification = SessionVerification(
                        False,
                        status=SESSION_STATUS_EXPIRED,
                        reason=reason,
                        branch="renew_persist_failed",
                        page_url=str(getattr(page, "url", "") or ""),
                        should_retry=True,
                    )
        except PlaywrightTimeoutError:
            renewed = False
            verification = SessionVerification(
                False,
                status=SESSION_STATUS_EXPIRED,
                reason="等待后台页面超时",
                branch="backend_page_timeout",
                page_url=str(getattr(page, "url", "") or ""),
                should_retry=True,
            )
        finally:
            try:
                temp_state_path.unlink(missing_ok=True)
            except OSError:
                pass
            close_page_fn(page)
            close_context_and_browser_fn(context, browser, state_path=None, persist_state=False)

    verification = SessionVerification(
        verification.valid,
        status=SESSION_STATUS_VALID if renewed else verification.status,
        actual_account_name=verification.actual_account_name,
        feedback_url=verification.feedback_url,
        reason=verification.reason,
        branch=verification.branch,
        page_url=verification.page_url,
        should_retry=verification.should_retry,
        should_relogin=verification.should_relogin,
        session_source=session_source_for_profile_dir(normalized_profile_dir),
    )
    apply_session_verification(account, verification, profile_dir=normalized_profile_dir, renewed=renewed)
    if renewed:
        log_fn(logger, f"账号 {account.name} 自动续期成功。")
    else:
        reason = f"：{verification.reason}" if verification.reason else ""
        extra = []
        if verification.branch:
            extra.append(f"判定分支={verification.branch}")
        if verification.page_url:
            extra.append(f"page.url={verification.page_url}")
        extra_text = f"（{'；'.join(extra)}）" if extra else ""
        log_fn(logger, f"账号 {account.name} 自动续期失败{reason}{extra_text}。")
        log_session_renew_failed(
            account.name,
            verification.reason or "未识别到可用后台登录态",
            branch=verification.branch,
            page_url=verification.page_url,
        )
    return renewed
