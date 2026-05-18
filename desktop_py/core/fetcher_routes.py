from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

CollectionCollector = Callable[..., dict[str, Any]]
FeedbackUrlBuilder = Callable[[str], str]


@dataclass(frozen=True)
class CollectionRoute:
    name: str
    step_label: str
    collect_fn: CollectionCollector


@dataclass(frozen=True)
class FeedbackRoute:
    name: str
    step_label: str
    build_feedback_url_fn: FeedbackUrlBuilder
    fallback_route: FeedbackRoute | None = None
