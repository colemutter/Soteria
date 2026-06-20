from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from include.swpc.endpoints import SWPC_ENDPOINTS
from include.swpc.fetch import (
    SwpcFetchResult,
    endpoint_metadata,
    fetch_swpc_endpoint_json,
)
from include.swpc.forecast_records import normalize_forecast_records
from include.swpc.schema import setup_swpc_schema


class SwpcWriter(Protocol):
    def get_endpoint_state(self, endpoint: str) -> dict[str, Any] | None: ...

    def upsert_endpoint_state(
        self,
        rows: Sequence[Mapping[str, Any]],
    ) -> list[tuple[Any, ...]]: ...

    def upsert_raw_payloads(
        self,
        rows: Sequence[Mapping[str, Any]],
        *,
        returning: Sequence[str] | str | None = None,
    ) -> list[tuple[Any, ...]]: ...

    def upsert_forecast_records(
        self,
        rows: Sequence[Mapping[str, Any]],
        *,
        returning: Sequence[str] | str | None = None,
    ) -> list[tuple[Any, ...]]: ...


@dataclass(frozen=True)
class EndpointIngestSummary:
    endpoint: str
    changed: bool
    fetched_at: str
    status_code: int
    raw_payload_id: str | None
    raw_payload_written: bool
    forecast_records: int
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def setup_database(writer: Any) -> None:
    setup_swpc_schema(writer)


def ingest_endpoint(
    writer: SwpcWriter,
    endpoint: Any,
    *,
    timeout: float = 30,
) -> EndpointIngestSummary:
    metadata = endpoint_metadata(endpoint)
    endpoint_state = writer.get_endpoint_state(metadata.path)
    result = fetch_swpc_endpoint_json(
        endpoint,
        endpoint_state=endpoint_state,
        timeout=timeout,
    )

    raw_payload_id = _write_raw_payload(writer, result)
    forecast_record_count = 0
    if result.raw_payload_row is not None:
        forecast_records = normalize_forecast_records(
            result.endpoint,
            result.raw_payload_row["payload_json"],
            result.fetched_at,
            raw_payload_id=raw_payload_id,
            source=metadata.family or "swpc",
        )
        if forecast_records:
            writer.upsert_forecast_records(forecast_records)
            forecast_record_count = len(forecast_records)

    state_row = dict(result.endpoint_state_row)
    if state_row.get("last_changed_at") is None and endpoint_state:
        state_row["last_changed_at"] = endpoint_state.get("last_changed_at")
    writer.upsert_endpoint_state([state_row])

    return EndpointIngestSummary(
        endpoint=result.endpoint,
        changed=result.changed,
        fetched_at=result.fetched_at,
        status_code=result.status_code,
        raw_payload_id=str(raw_payload_id) if raw_payload_id is not None else None,
        raw_payload_written=result.raw_payload_row is not None,
        forecast_records=forecast_record_count,
        error=result.error,
    )


def ingest_all_endpoints(
    writer: SwpcWriter,
    *,
    endpoints: Sequence[Any] = SWPC_ENDPOINTS,
    timeout: float = 30,
) -> list[EndpointIngestSummary]:
    return [
        ingest_endpoint(writer, endpoint, timeout=timeout)
        for endpoint in endpoints
    ]


def summarize_ingest(results: Sequence[EndpointIngestSummary | Mapping[str, Any]]) -> dict[str, Any]:
    rows = [result.to_dict() if isinstance(result, EndpointIngestSummary) else dict(result) for result in results]
    changed = [row["endpoint"] for row in rows if row.get("changed")]
    errors = [row for row in rows if row.get("error")]
    return {
        "endpoint_count": len(rows),
        "changed_endpoint_count": len(changed),
        "changed_endpoints": changed,
        "raw_payload_rows": sum(1 for row in rows if row.get("raw_payload_written")),
        "forecast_records": sum(int(row.get("forecast_records") or 0) for row in rows),
        "error_count": len(errors),
        "errors": errors,
    }


def _write_raw_payload(writer: SwpcWriter, result: SwpcFetchResult) -> Any | None:
    if result.raw_payload_row is None:
        return None
    returned = writer.upsert_raw_payloads([result.raw_payload_row], returning="id")
    if not returned:
        return None
    return returned[0][0]


__all__ = [
    "EndpointIngestSummary",
    "ingest_all_endpoints",
    "ingest_endpoint",
    "setup_database",
    "summarize_ingest",
]
