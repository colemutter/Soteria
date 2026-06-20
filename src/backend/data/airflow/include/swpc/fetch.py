from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any, Protocol
from urllib.error import HTTPError
from urllib.request import Request, build_opener

from include.swpc.endpoints import SWPC_ORIGIN


JsonPayload = Any
RawPayloadRow = dict[str, Any]
EndpointStateRow = dict[str, Any]
EndpointInput = Any
RawUriBuilder = Callable[[str, str, str], str | None]
RAW_PAYLOAD_UPDATE_COLUMNS = (
    "fetched_at",
    "response_status",
    "etag",
    "last_modified",
    "content_type",
    "raw_uri",
)


class RawPayloadWriter(Protocol):
    def upsert_rows(
        self,
        table: str,
        rows: Sequence[Mapping[str, Any]],
        *,
        conflict_columns: Sequence[str],
        update_columns: Sequence[str] | None = None,
        returning: Sequence[str] | str | None = None,
    ) -> list[tuple[Any, ...]]: ...


@dataclass(frozen=True)
class EndpointMetadata:
    path: str
    family: str | None = None
    cadence_seconds: int | None = None
    protection_tier: str | None = None


@dataclass(frozen=True)
class SwpcFetchResult:
    endpoint: str
    changed: bool
    fetched_at: str
    raw_uri: str | None
    etag: str | None
    last_modified: str | None
    payload_hash: str | None
    status_code: int
    content_type: str | None
    raw_payload_row: RawPayloadRow | None
    endpoint_state_row: EndpointStateRow
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class InvalidJsonPayloadError(ValueError):
    """Raised internally when SWPC responds with bytes that are not JSON."""


def canonical_json(payload: JsonPayload) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def payload_sha256(payload: JsonPayload) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def swpc_url(path: str, origin: str = SWPC_ORIGIN) -> str:
    if path.startswith(("http://", "https://")):
        return path
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{origin.rstrip('/')}{path}"


def conditional_headers(endpoint_state: Mapping[str, Any] | None) -> dict[str, str]:
    if not endpoint_state:
        return {}

    headers: dict[str, str] = {}
    etag = endpoint_state.get("etag")
    last_modified = endpoint_state.get("last_modified")
    if etag:
        headers["If-None-Match"] = str(etag)
    if last_modified:
        headers["If-Modified-Since"] = str(last_modified)
    return headers


def build_raw_payload_row(
    *,
    endpoint: EndpointInput,
    source_url: str,
    fetched_at: str,
    response_status: int,
    etag: str | None,
    last_modified: str | None,
    content_type: str | None,
    payload: JsonPayload,
    raw_uri: str | None = None,
) -> RawPayloadRow:
    metadata = endpoint_metadata(endpoint)
    return {
        "endpoint": metadata.path,
        "family": metadata.family,
        "protection_tier": metadata.protection_tier,
        "cadence_seconds": metadata.cadence_seconds,
        "source_url": source_url,
        "fetched_at": fetched_at,
        "response_status": response_status,
        "etag": etag,
        "last_modified": last_modified,
        "content_type": content_type,
        "payload_hash": payload_sha256(payload),
        "payload_json": payload,
        "raw_uri": raw_uri,
    }


def build_endpoint_state_row(
    *,
    endpoint: str,
    fetched_at: str,
    status_code: int,
    etag: str | None,
    last_modified: str | None,
    payload_hash: str | None,
    changed: bool,
    error: str | None = None,
) -> EndpointStateRow:
    return {
        "endpoint": endpoint,
        "etag": etag,
        "last_modified": last_modified,
        "payload_hash": payload_hash,
        "last_fetched_at": fetched_at,
        "last_changed_at": fetched_at if changed else None,
        "last_status_code": status_code,
        "last_error": error,
    }


def fetch_swpc_endpoint_json(
    endpoint: EndpointInput,
    *,
    endpoint_state: Mapping[str, Any] | None = None,
    opener: Any | None = None,
    now: dt.datetime | None = None,
    origin: str = SWPC_ORIGIN,
    timeout: float = 30,
    raw_uri_builder: RawUriBuilder | None = None,
) -> SwpcFetchResult:
    metadata = endpoint_metadata(endpoint)
    fetched_at = _iso_utc(now or dt.datetime.now(dt.UTC))
    url = swpc_url(metadata.path, origin=origin)
    request = Request(url, headers=_request_headers(endpoint_state))
    opener = opener or build_opener()

    try:
        with opener.open(request, timeout=timeout) as response:
            status_code = _response_status(response)
            headers = getattr(response, "headers", {})
            etag = _header_value(headers, "ETag") or _state_value(
                endpoint_state, "etag"
            )
            last_modified = _header_value(headers, "Last-Modified") or _state_value(
                endpoint_state, "last_modified"
            )
            content_type = _header_value(headers, "Content-Type")
            try:
                payload = _load_json(response.read())
            except InvalidJsonPayloadError as exc:
                error = f"invalid_json: {exc}"
                return _unchanged_result(
                    endpoint=metadata.path,
                    fetched_at=fetched_at,
                    status_code=status_code,
                    etag=etag,
                    last_modified=last_modified,
                    content_type=content_type,
                    payload_hash=_state_value(endpoint_state, "payload_hash"),
                    error=error,
                )

    except HTTPError as exc:
        if exc.code != 304:
            raise
        etag = _header_value(exc.headers, "ETag") or _state_value(endpoint_state, "etag")
        last_modified = _header_value(exc.headers, "Last-Modified") or _state_value(
            endpoint_state, "last_modified"
        )
        return _unchanged_result(
            endpoint=metadata.path,
            fetched_at=fetched_at,
            status_code=304,
            etag=etag,
            last_modified=last_modified,
            content_type=_header_value(exc.headers, "Content-Type"),
            payload_hash=_state_value(endpoint_state, "payload_hash"),
            error=None,
        )

    payload_hash = payload_sha256(payload)
    raw_uri = (
        raw_uri_builder(metadata.path, fetched_at, payload_hash)
        if raw_uri_builder
        else None
    )
    raw_payload_row = build_raw_payload_row(
        endpoint=endpoint,
        source_url=url,
        fetched_at=fetched_at,
        response_status=status_code,
        etag=etag,
        last_modified=last_modified,
        content_type=content_type,
        payload=payload,
        raw_uri=raw_uri,
    )
    state_row = build_endpoint_state_row(
        endpoint=metadata.path,
        fetched_at=fetched_at,
        status_code=status_code,
        etag=etag,
        last_modified=last_modified,
        payload_hash=payload_hash,
        changed=True,
    )
    return SwpcFetchResult(
        endpoint=metadata.path,
        changed=True,
        fetched_at=fetched_at,
        raw_uri=raw_uri,
        etag=etag,
        last_modified=last_modified,
        payload_hash=payload_hash,
        status_code=status_code,
        content_type=content_type,
        raw_payload_row=raw_payload_row,
        endpoint_state_row=state_row,
    )


def upsert_raw_payload_row(
    writer: RawPayloadWriter,
    row: Mapping[str, Any],
    *,
    returning: Sequence[str] | str | None = None,
) -> list[tuple[Any, ...]]:
    return writer.upsert_rows(
        "swpc_raw_payloads",
        [row],
        conflict_columns=["endpoint", "payload_hash"],
        update_columns=RAW_PAYLOAD_UPDATE_COLUMNS,
        returning=returning,
    )


def upsert_fetch_result_raw_payload(
    writer: RawPayloadWriter,
    result: SwpcFetchResult,
    *,
    returning: Sequence[str] | str | None = None,
) -> list[tuple[Any, ...]]:
    if result.raw_payload_row is None:
        return []
    return upsert_raw_payload_row(writer, result.raw_payload_row, returning=returning)


def endpoint_metadata(endpoint: EndpointInput) -> EndpointMetadata:
    if isinstance(endpoint, str):
        return EndpointMetadata(path=endpoint)
    if isinstance(endpoint, Mapping):
        return EndpointMetadata(
            path=str(endpoint["path"]),
            family=_optional_str(endpoint.get("family")),
            cadence_seconds=_optional_int(endpoint.get("cadence_seconds")),
            protection_tier=_optional_str(endpoint.get("protection_tier")),
        )
    return EndpointMetadata(
        path=str(endpoint.path),
        family=_optional_str(getattr(endpoint, "family", None)),
        cadence_seconds=_optional_int(getattr(endpoint, "cadence_seconds", None)),
        protection_tier=_optional_str(getattr(endpoint, "protection_tier", None)),
    )


def _request_headers(endpoint_state: Mapping[str, Any] | None) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "Soteria-SWPC-ETL/0.1",
    }
    headers.update(conditional_headers(endpoint_state))
    return headers


def _unchanged_result(
    *,
    endpoint: str,
    fetched_at: str,
    status_code: int,
    etag: str | None,
    last_modified: str | None,
    content_type: str | None,
    payload_hash: str | None,
    error: str | None,
) -> SwpcFetchResult:
    state_row = build_endpoint_state_row(
        endpoint=endpoint,
        fetched_at=fetched_at,
        status_code=status_code,
        etag=etag,
        last_modified=last_modified,
        payload_hash=payload_hash,
        changed=False,
        error=error,
    )
    return SwpcFetchResult(
        endpoint=endpoint,
        changed=False,
        fetched_at=fetched_at,
        raw_uri=None,
        etag=etag,
        last_modified=last_modified,
        payload_hash=payload_hash,
        status_code=status_code,
        content_type=content_type,
        raw_payload_row=None,
        endpoint_state_row=state_row,
        error=error,
    )


def _load_json(body: bytes) -> JsonPayload:
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidJsonPayloadError(str(exc)) from exc


def _response_status(response: Any) -> int:
    status = getattr(response, "status", None)
    if status is not None:
        return int(status)
    return int(response.getcode())


def _header_value(headers: Any, name: str) -> str | None:
    if headers is None:
        return None
    value = headers.get(name)
    if value is not None:
        return str(value)
    if isinstance(headers, Mapping):
        lower_name = name.lower()
        for key, candidate in headers.items():
            if str(key).lower() == lower_name and candidate is not None:
                return str(candidate)
    return None


def _state_value(endpoint_state: Mapping[str, Any] | None, key: str) -> str | None:
    if not endpoint_state:
        return None
    value = endpoint_state.get(key)
    return str(value) if value is not None else None


def _iso_utc(value: dt.datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.UTC)
    return value.astimezone(dt.UTC).isoformat().replace("+00:00", "Z")


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None


def _optional_int(value: Any) -> int | None:
    return int(value) if value is not None else None


__all__ = [
    "EndpointMetadata",
    "RAW_PAYLOAD_UPDATE_COLUMNS",
    "SwpcFetchResult",
    "build_endpoint_state_row",
    "build_raw_payload_row",
    "canonical_json",
    "conditional_headers",
    "endpoint_metadata",
    "fetch_swpc_endpoint_json",
    "payload_sha256",
    "swpc_url",
    "upsert_fetch_result_raw_payload",
    "upsert_raw_payload_row",
]
