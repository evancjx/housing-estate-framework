"""Build, validate, and atomically publish source-receipt sidecars."""

from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Mapping

from sg_estate.contracts import (
    ContractError,
    SOURCE_RECEIPT,
    SOURCE_RECEIPT_SCHEMA_VERSION,
)


RECEIPT_SUFFIX = ".receipt.json"


def sha256_file(path: str | Path) -> str:
    """Return the lowercase SHA-256 digest of a file's exact bytes."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def receipt_path_for(output_path: str | Path) -> Path:
    """Return the receipt sidecar path beside a staged output."""

    output = Path(output_path)
    return output.with_name(f"{output.name}{RECEIPT_SUFFIX}")


def _timestamp_text(value: datetime | str | None) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _date_text(value: date | str | None) -> str | None:
    if isinstance(value, datetime):
        raise ContractError("coverage boundaries must be dates, not timestamps")
    if isinstance(value, date):
        return value.isoformat()
    return value


def build_source_receipt(
    output_path: str | Path,
    *,
    dataset_id: str,
    authority: str,
    source_url: str | None = None,
    source_urls: list[str] | tuple[str, ...] | None = None,
    source_identity: str | None = None,
    retrieved_at: datetime | str | None = None,
    coverage_start: date | str | None = None,
    coverage_end: date | str | None = None,
    row_count: int | None = None,
    cache_state: str,
    fallback_state: str,
    validation_status: str,
) -> dict[str, object]:
    """Build a validated v2 receipt for the exact staged-output bytes.

    Time and coverage values default to ``None`` intentionally. Callers must
    supply evidence; this helper never substitutes the current time or a file
    modification time for unknown provenance.
    """

    output = Path(output_path)
    if not output.is_file():
        raise FileNotFoundError(f"staged output not found: {output}")

    receipt: dict[str, object] = {
        "schema_version": SOURCE_RECEIPT_SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "authority": authority,
        "source_url": source_url,
        "source_urls": list(source_urls) if source_urls is not None else None,
        "source_identity": source_identity,
        "retrieved_at": _timestamp_text(retrieved_at),
        "coverage_start": _date_text(coverage_start),
        "coverage_end": _date_text(coverage_end),
        "row_count": row_count,
        "sha256": sha256_file(output),
        "cache_state": cache_state,
        "fallback_state": fallback_state,
        "validation_status": validation_status,
    }
    return SOURCE_RECEIPT.validate(receipt, source=f"receipt for {output}")


def validate_receipt_for_output(
    receipt: Mapping[str, object],
    output_path: str | Path,
    *,
    source: str = "source receipt",
) -> dict[str, object]:
    """Validate receipt structure and bind it to the staged output bytes."""

    output = Path(output_path)
    if not output.is_file():
        raise FileNotFoundError(f"staged output not found: {output}")
    validated = SOURCE_RECEIPT.validate(receipt, source=source)
    expected = validated["sha256"]
    if expected is None:
        raise ContractError(f"{source}.sha256 is required for a staged output")
    actual = sha256_file(output)
    if expected != actual:
        raise ContractError(
            f"{source}.sha256 does not match {output}: expected {expected}, got {actual}"
        )
    return validated


def write_source_receipt(
    output_path: str | Path,
    receipt: Mapping[str, object],
) -> Path:
    """Atomically write a validated receipt beside its staged output.

    The existing sidecar is left untouched if validation, serialization, file
    synchronization, or replacement fails.
    """

    output = Path(output_path)
    destination = receipt_path_for(output)
    validated = validate_receipt_for_output(
        receipt,
        output,
        source=str(destination),
    )
    encoded = json.dumps(validated, ensure_ascii=False, indent=2) + "\n"

    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def read_source_receipt(
    receipt_path: str | Path,
    *,
    output_path: str | Path | None = None,
) -> dict[str, object]:
    """Read a receipt and optionally verify it against its staged output."""

    path = Path(receipt_path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid source receipt JSON: {path}: {exc}") from exc
    if output_path is None:
        return SOURCE_RECEIPT.validate(value, source=str(path))
    return validate_receipt_for_output(value, output_path, source=str(path))


def receipt_acquisition_mode(receipt: Mapping[str, object]) -> str:
    """Return the receipt's explicit acquisition mode.

    A reviewed fallback takes precedence over the cache state. Other values are
    one of fresh, cached, mixed, offline, derived, or unknown.
    """

    validated = SOURCE_RECEIPT.validate(receipt)
    if validated["fallback_state"] == "used":
        return "fallback"
    return str(validated["cache_state"])


__all__ = [
    "RECEIPT_SUFFIX",
    "build_source_receipt",
    "read_source_receipt",
    "receipt_acquisition_mode",
    "receipt_path_for",
    "sha256_file",
    "validate_receipt_for_output",
    "write_source_receipt",
]
