from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from desktop_py.core.fetcher_rules import DEFAULT_FETCH_RULE_VERSION
from desktop_py.core.models import AccountConfig, FetchResult
from desktop_py.core.store import write_account_output_json


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class FetchEvidenceRecord:
    kind: str
    label: str
    path: str = ""
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FetchStepRecord:
    name: str
    status: str
    started_at: str
    finished_at: str = ""
    duration_ms: int = 0
    detail: str = ""
    error_type: str = ""
    error_message: str = ""
    evidence: list[FetchEvidenceRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evidence"] = [item.to_dict() for item in self.evidence]
        return payload


@dataclass
class FetchRunManifest:
    run_id: str
    account_name: str
    started_at: str
    status: str = "running"
    finished_at: str = ""
    duration_ms: int = 0
    profile_dir: str = ""
    output_dir: str = ""
    rule_version: str = DEFAULT_FETCH_RULE_VERSION
    result_ok: bool | None = None
    result_note: str = ""
    error_type: str = ""
    error_message: str = ""
    steps: list[FetchStepRecord] = field(default_factory=list)
    evidence: list[FetchEvidenceRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["steps"] = [item.to_dict() for item in self.steps]
        payload["evidence"] = [item.to_dict() for item in self.evidence]
        return payload


def start_fetch_run(account: AccountConfig, *, profile_dir: str = "", output_dir: str = "") -> FetchRunManifest:
    return FetchRunManifest(
        run_id=uuid.uuid4().hex,
        account_name=account.name,
        started_at=_now_text(),
        profile_dir=profile_dir,
        output_dir=output_dir,
    )


@contextmanager
def fetch_step(
    manifest: FetchRunManifest,
    name: str,
    *,
    detail: str = "",
    evidence: list[FetchEvidenceRecord] | None = None,
) -> Iterator[FetchStepRecord]:
    started = time.monotonic()
    step = FetchStepRecord(
        name=name,
        status="running",
        started_at=_now_text(),
        detail=detail,
        evidence=list(evidence or []),
    )
    try:
        yield step
    except Exception as exc:
        step.status = "failed"
        step.error_type = type(exc).__name__
        step.error_message = str(exc)
        raise
    else:
        step.status = "ok"
    finally:
        step.finished_at = _now_text()
        step.duration_ms = int((time.monotonic() - started) * 1000)
        manifest.steps.append(step)


def add_fetch_evidence(
    manifest: FetchRunManifest,
    *,
    kind: str,
    label: str,
    path: str = "",
    summary: str = "",
    metadata: dict[str, Any] | None = None,
) -> FetchEvidenceRecord:
    evidence = FetchEvidenceRecord(
        kind=kind,
        label=label,
        path=path,
        summary=summary,
        metadata=dict(metadata or {}),
    )
    manifest.evidence.append(evidence)
    return evidence


def finish_fetch_run(
    manifest: FetchRunManifest,
    *,
    result: FetchResult | None = None,
    error: BaseException | None = None,
) -> None:
    manifest.finished_at = _now_text()
    try:
        started = datetime.strptime(manifest.started_at, "%Y-%m-%d %H:%M:%S")
        finished = datetime.strptime(manifest.finished_at, "%Y-%m-%d %H:%M:%S")
        manifest.duration_ms = max(0, int((finished - started).total_seconds() * 1000))
    except ValueError:
        manifest.duration_ms = 0

    if error is not None:
        manifest.status = "failed"
        manifest.error_type = type(error).__name__
        manifest.error_message = str(error)
        return

    manifest.status = "ok" if result is None or result.ok else "failed"
    if result is not None:
        manifest.result_ok = result.ok
        manifest.result_note = result.note


def write_fetch_manifest(account_name: str, manifest: FetchRunManifest) -> None:
    write_account_output_json(account_name, "fetch_manifest.json", manifest.to_dict())
