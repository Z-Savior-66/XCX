from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from desktop_py.core.fetcher_common import fetch_error_code
from desktop_py.core.fetcher_rules import DEFAULT_FETCH_RULE_VERSION
from desktop_py.core.models import AccountConfig, FetchResult
from desktop_py.core.store import write_account_output_json, write_diagnostic_index_json


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
    error_code: str = ""
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
    error_code: str = ""
    error_type: str = ""
    error_message: str = ""
    steps: list[FetchStepRecord] = field(default_factory=list)
    evidence: list[FetchEvidenceRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["steps"] = [item.to_dict() for item in self.steps]
        payload["evidence"] = [item.to_dict() for item in self.evidence]
        return payload


@dataclass
class BatchDiagnosticAccountRecord:
    account_name: str
    status: str
    ok: bool | None = None
    note: str = ""
    error_code: str = ""
    error_type: str = ""
    error_message: str = ""
    duration_ms: int = 0
    manifest_path: str = ""
    result_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BatchDiagnosticIndex:
    run_id: str
    started_at: str
    total_accounts: int
    profile_dir: str = ""
    status: str = "running"
    finished_at: str = ""
    duration_ms: int = 0
    success_count: int = 0
    failure_count: int = 0
    cancelled_count: int = 0
    error_code: str = ""
    error_type: str = ""
    error_message: str = ""
    accounts: list[BatchDiagnosticAccountRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["accounts"] = [item.to_dict() for item in self.accounts]
        return payload


def start_fetch_run(account: AccountConfig, *, profile_dir: str = "", output_dir: str = "") -> FetchRunManifest:
    return FetchRunManifest(
        run_id=uuid.uuid4().hex,
        account_name=account.name,
        started_at=_now_text(),
        profile_dir=profile_dir,
        output_dir=output_dir,
    )


def start_batch_diagnostic_index(*, total_accounts: int, profile_dir: str = "") -> BatchDiagnosticIndex:
    return BatchDiagnosticIndex(
        run_id=uuid.uuid4().hex,
        started_at=_now_text(),
        total_accounts=total_accounts,
        profile_dir=profile_dir,
    )


def add_batch_diagnostic_account(
    index: BatchDiagnosticIndex,
    *,
    account_name: str,
    result: FetchResult | None = None,
    error: BaseException | None = None,
    duration_ms: int = 0,
    manifest_path: str = "",
    result_path: str = "",
) -> BatchDiagnosticAccountRecord:
    status = "ok"
    ok = True
    note = ""
    error_code = ""
    error_type = ""
    error_message = ""
    if result is not None:
        ok = result.ok
        note = result.note
        status = "ok" if result.ok else "failed"
    if error is not None:
        ok = False
        note = str(error)
        error_code = fetch_error_code(error)
        error_type = type(error).__name__
        error_message = str(error)
        status = "cancelled" if error_type == "CancelledError" else "failed"

    record = BatchDiagnosticAccountRecord(
        account_name=account_name,
        status=status,
        ok=ok,
        note=note,
        error_code=error_code,
        error_type=error_type,
        error_message=error_message,
        duration_ms=duration_ms,
        manifest_path=manifest_path,
        result_path=result_path,
    )
    index.accounts.append(record)
    return record


def finish_batch_diagnostic_index(
    index: BatchDiagnosticIndex,
    *,
    error: BaseException | None = None,
) -> None:
    index.finished_at = _now_text()
    try:
        started = datetime.strptime(index.started_at, "%Y-%m-%d %H:%M:%S")
        finished = datetime.strptime(index.finished_at, "%Y-%m-%d %H:%M:%S")
        index.duration_ms = max(0, int((finished - started).total_seconds() * 1000))
    except ValueError:
        index.duration_ms = 0
    index.success_count = sum(1 for item in index.accounts if item.status == "ok")
    index.failure_count = sum(1 for item in index.accounts if item.status == "failed")
    index.cancelled_count = sum(1 for item in index.accounts if item.status == "cancelled")

    if error is not None:
        index.error_code = fetch_error_code(error)
        index.error_type = type(error).__name__
        index.error_message = str(error)
        index.status = "cancelled" if index.error_type == "CancelledError" else "failed"
        return
    index.status = "failed" if index.failure_count or index.cancelled_count else "ok"


def _evidence_records_from_error(error: BaseException) -> list[FetchEvidenceRecord]:
    records: list[FetchEvidenceRecord] = []
    for item in getattr(error, "evidence", []) or []:
        if not isinstance(item, dict):
            continue
        records.append(
            FetchEvidenceRecord(
                kind=str(item.get("kind", "") or ""),
                label=str(item.get("label", "") or ""),
                path=str(item.get("path", "") or ""),
                summary=str(item.get("summary", "") or ""),
                metadata=dict(item.get("metadata", {}) or {}),
            )
        )
    return records


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
        step.error_code = fetch_error_code(exc)
        step.error_type = type(exc).__name__
        step.error_message = str(exc)
        step.evidence.extend(_evidence_records_from_error(exc))
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
        manifest.error_code = fetch_error_code(error)
        manifest.error_type = type(error).__name__
        manifest.error_message = str(error)
        manifest.evidence.extend(_evidence_records_from_error(error))
        return

    manifest.status = "ok" if result is None or result.ok else "failed"
    if result is not None:
        manifest.result_ok = result.ok
        manifest.result_note = result.note


def write_fetch_manifest(account_name: str, manifest: FetchRunManifest) -> None:
    write_account_output_json(account_name, "fetch_manifest.json", manifest.to_dict())


def write_batch_diagnostic_index(index: BatchDiagnosticIndex) -> None:
    write_diagnostic_index_json(index.to_dict())
