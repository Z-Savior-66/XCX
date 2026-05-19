from __future__ import annotations

import json
import re
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Response

from desktop_py.core.fetcher_rules import DEFAULT_NOTIFICATION_RULES, DEFAULT_REFUND_RULES, deadline_field_score
from desktop_py.core.parser import convert_timestamp

TARGET_REFUND_RESPONSE_URL_KEYWORDS = DEFAULT_REFUND_RULES.response_url_keywords
TARGET_NOTIFICATION_RESPONSE_URL_KEYWORDS = DEFAULT_NOTIFICATION_RULES.response_url_keywords


def _fallback_from_responses(responses: list[Any]) -> str:
    candidates: list[tuple[int, str]] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                next_path = f"{path}.{key}" if path else key
                visit(item, next_path)
            return

        if isinstance(value, list):
            for index, item in enumerate(value):
                next_path = f"{path}[{index}]"
                visit(item, next_path)
            return

        if value is None:
            return

        text = str(value).strip()
        if not text:
            return

        normalized = convert_timestamp(text)
        matched = re.search(r"20\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}(?:[日\sT]*\d{1,2}:\d{2}(?::\d{2})?)?", normalized)
        if not matched:
            return

        score = deadline_field_score(path)

        if score > 0:
            candidates.append((score, matched.group(0)))

    visit(responses, "$")
    if not candidates:
        return ""
    return max(candidates, key=lambda item: item[0])[1]


def extract_response_token(response_url: str) -> str:
    return (parse_qs(urlparse(response_url).query).get("token") or [""])[0].strip()


def classify_refund_response_type(response_url: str, body: Any) -> str:
    url = response_url.strip().lower()
    if "getiaprefundlist" in url:
        return "list"
    if DEFAULT_REFUND_RULES.list_response_keyword in url:
        if any(marker in url for marker in DEFAULT_REFUND_RULES.detail_query_markers):
            return "detail"
        return "list"
    if any(keyword in url for keyword in DEFAULT_REFUND_RULES.detail_response_keywords):
        return "detail"

    body_text = str(body)
    if "user_refund_check_list" in body_text:
        return "detail" if any(marker in url for marker in DEFAULT_REFUND_RULES.detail_query_markers) else "list"
    return "other"


def _is_target_refund_response_url(response_url: str) -> bool:
    url = response_url.strip().lower()
    return any(keyword in url for keyword in TARGET_REFUND_RESPONSE_URL_KEYWORDS)


def _is_target_notification_response_url(response_url: str) -> bool:
    url = response_url.strip().lower()
    return any(keyword in url for keyword in TARGET_NOTIFICATION_RESPONSE_URL_KEYWORDS)


def _capture_response_payload(response: Response) -> Any | None:
    if not (_is_target_refund_response_url(response.url) or _is_target_notification_response_url(response.url)):
        return None
    content_type = (response.headers.get("content-type") or "").lower()
    if not any(keyword in content_type for keyword in ("json", "javascript", "text")):
        return None

    try:
        text = response.text()
    except Exception:
        return None

    if not text.strip():
        return None

    try:
        body: Any = json.loads(text)
    except Exception:
        body = text[:3000]

    response_type = classify_refund_response_type(response.url, body)
    if response_type == "other" and _is_target_notification_response_url(response.url):
        response_type = "notification"
    return {
        "url": response.url,
        "status": response.status,
        "content_type": content_type,
        "body": body,
        "token": extract_response_token(response.url),
        "response_type": response_type,
        "captured_at": time.time(),
    }
