from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from desktop_py.core.store import DATA_DIR

DEFAULT_FETCH_RULE_VERSION = "2026-05-14.v1"
TRANSACTION_COMPLAINT_RULES_FILE_NAME = "transaction_complaint_rules.json"


@dataclass(frozen=True)
class DeadlineFieldRule:
    key: str
    score: int


@dataclass(frozen=True)
class RuleMatchResult:
    matched: bool
    rule_name: str = ""
    rule_version: str = ""
    expected_value: str = ""


@dataclass(frozen=True)
class RefundRuleSet:
    version: str
    iframe_selectors: tuple[str, ...]
    iframe_ready_markers: tuple[str, ...]
    empty_list_markers: tuple[str, ...]
    pending_text_markers: tuple[str, ...]
    non_empty_body_markers: tuple[str, ...]
    zero_count_markers: tuple[str, ...]
    response_url_keywords: tuple[str, ...]
    list_response_keyword: str
    detail_response_keywords: tuple[str, ...]
    detail_query_markers: tuple[str, ...]
    deadline_fields: tuple[DeadlineFieldRule, ...]


@dataclass(frozen=True)
class NotificationRuleSet:
    version: str
    center_url_keyword: str
    response_url_keywords: tuple[str, ...]
    container_selector: str
    item_selector: str
    entry_text: str
    target_titles: dict[str, str]


@dataclass(frozen=True)
class TransactionComplaintRuleSet:
    version: str
    target_account_names: tuple[str, ...]
    pending_status: int
    pending_status_text: str
    page_size: int


DEFAULT_REFUND_RULES = RefundRuleSet(
    version=DEFAULT_FETCH_RULE_VERSION,
    iframe_selectors=(
        "#js_iframe",
        "iframe[src*='gameFeedback']",
        "iframe[src*='refund']",
    ),
    iframe_ready_markers=(
        "退款申请",
        "处理截止时间",
        "处理",
        "暂无内容",
    ),
    empty_list_markers=("退款申请(0)",),
    pending_text_markers=(
        "处理截止时间",
        "退款申请(",
        "处理",
    ),
    non_empty_body_markers=(
        "处理截止时间",
        "refund",
        "deadline",
        "申请单",
        "退款申请",
    ),
    zero_count_markers=(
        "退款申请(0)",
        '"count": 0',
        "'count': 0",
    ),
    response_url_keywords=(
        "getuserrefundchecklist",
        "checkuserrefundcheck",
        "getpayorderlistforuserrefund",
        "getiaprefundlist",
    ),
    list_response_keyword="getuserrefundchecklist",
    detail_response_keywords=(
        "checkuserrefundcheck",
        "getpayorderlistforuserrefund",
    ),
    detail_query_markers=(
        "cid=",
        "openid=",
    ),
    deadline_fields=(
        DeadlineFieldRule("appeal_deadline_time", 100),
        DeadlineFieldRule("deadline_time", 95),
        DeadlineFieldRule("deadline", 90),
    ),
)

DEFAULT_NOTIFICATION_RULES = NotificationRuleSet(
    version=DEFAULT_FETCH_RULE_VERSION,
    center_url_keyword="/wxamp/tools/wasysnotify",
    response_url_keywords=(
        "/wxamp/tools/wasysnotify",
        "wasysnotify",
    ),
    container_selector="div.page_notice",
    item_selector="dl.notice_item.js_msg_item",
    entry_text="通知中心",
    target_titles={
        "annual_review": "小程序微信认证年审通知",
        "copyright_complaint": "你的账号收到一条侵权投诉",
    },
)

DEFAULT_TRANSACTION_COMPLAINT_RULES = TransactionComplaintRuleSet(
    version=DEFAULT_FETCH_RULE_VERSION,
    target_account_names=("当代情诗摘抄合集", "经典诗词摘抄"),
    pending_status=201,
    pending_status_text="待处理",
    page_size=50,
)


def transaction_complaint_rules_file(path: Path | None = None) -> Path:
    if path is not None:
        return path
    data_path = DATA_DIR / TRANSACTION_COMPLAINT_RULES_FILE_NAME
    if data_path.exists():
        return data_path
    return Path(__file__).resolve().with_name(TRANSACTION_COMPLAINT_RULES_FILE_NAME)


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except TypeError, ValueError:
        return default


def _string_tuple(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    if not isinstance(value, list):
        return default
    return tuple(text for item in value if (text := str(item).strip()))


def transaction_complaint_rules_from_mapping(
    mapping: dict[str, Any],
    *,
    default_rules: TransactionComplaintRuleSet = DEFAULT_TRANSACTION_COMPLAINT_RULES,
) -> TransactionComplaintRuleSet:
    pending_status = _safe_int(
        mapping.get("pending_status", default_rules.pending_status), default_rules.pending_status
    )
    page_size = max(1, _safe_int(mapping.get("page_size", default_rules.page_size), default_rules.page_size))
    return TransactionComplaintRuleSet(
        version=str(mapping.get("version", default_rules.version) or default_rules.version).strip()
        or default_rules.version,
        target_account_names=_string_tuple(mapping.get("target_account_names"), default_rules.target_account_names),
        pending_status=pending_status,
        pending_status_text=str(
            mapping.get("pending_status_text", default_rules.pending_status_text) or default_rules.pending_status_text
        ).strip()
        or default_rules.pending_status_text,
        page_size=page_size,
    )


def load_transaction_complaint_rules(path: Path | None = None) -> TransactionComplaintRuleSet:
    rules_file = transaction_complaint_rules_file(path)
    try:
        payload = json.loads(rules_file.read_text(encoding="utf-8-sig"))
    except OSError, json.JSONDecodeError:
        return DEFAULT_TRANSACTION_COMPLAINT_RULES
    if not isinstance(payload, dict):
        return DEFAULT_TRANSACTION_COMPLAINT_RULES
    return transaction_complaint_rules_from_mapping(payload)


def deadline_field_score(path: str, rules: RefundRuleSet = DEFAULT_REFUND_RULES) -> int:
    path_lower = path.lower()
    for field_rule in rules.deadline_fields:
        if field_rule.key in path_lower:
            return field_rule.score
    return 0


def match_notification_title(title: str, rules: NotificationRuleSet = DEFAULT_NOTIFICATION_RULES) -> RuleMatchResult:
    normalized_title = title.strip()
    if not normalized_title:
        return RuleMatchResult(False, rule_version=rules.version)
    for rule_name, expected_title in rules.target_titles.items():
        if normalized_title == expected_title:
            return RuleMatchResult(
                True,
                rule_name=rule_name,
                rule_version=rules.version,
                expected_value=expected_title,
            )
    return RuleMatchResult(False, rule_version=rules.version)
