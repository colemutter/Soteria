from __future__ import annotations

import datetime as dt
import sys
import unittest
from pathlib import Path
from typing import Any
from urllib.error import HTTPError


AIRFLOW_ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = AIRFLOW_ROOT.parent
for path in (AIRFLOW_ROOT, DATA_ROOT):
    path_string = str(path)
    if path_string not in sys.path:
        sys.path.insert(0, path_string)

from include.swpc.fetch import (  # noqa: E402
    RAW_PAYLOAD_UPDATE_COLUMNS,
    canonical_json,
    fetch_swpc_endpoint_json,
    payload_sha256,
    upsert_raw_payload_row,
)
from include.swpc.schema import (  # noqa: E402
    CREATE_SWPC_FORECAST_RECORDS_TABLE,
    CREATE_SWPC_RAW_PAYLOADS_TABLE,
    SWPC_SCHEMA_STATEMENTS,
    setup_swpc_schema,
)


class FakeResponse:
    def __init__(
        self,
        body: bytes,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._body = body
        self.status = status
        self.headers = headers or {}

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


class FakeOpener:
    def __init__(
        self,
        response: FakeResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.request: Any | None = None
        self.timeout: float | None = None

    def open(self, request: Any, *, timeout: float) -> FakeResponse:
        self.request = request
        self.timeout = timeout
        if self.error is not None:
            raise self.error
        if self.response is None:
            raise AssertionError("FakeOpener needs a response or error")
        return self.response


class FakeWriter:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.upserts: list[dict[str, Any]] = []

    def execute(self, query: str, params: tuple[object, ...] = ()) -> None:
        self.executed.append(query)

    def upsert_rows(
        self,
        table: str,
        rows: list[dict[str, Any]],
        *,
        conflict_columns: list[str],
        update_columns: list[str] | None = None,
        returning: list[str] | str | None = None,
    ) -> list[tuple[Any, ...]]:
        self.upserts.append(
            {
                "table": table,
                "rows": rows,
                "conflict_columns": conflict_columns,
                "update_columns": update_columns,
                "returning": returning,
            }
        )
        return [("ok",)]


class SwpcFetchSchemaTest(unittest.TestCase):
    def test_payload_hash_uses_canonical_json_object_order(self) -> None:
        left = {"b": 2, "a": {"y": 1, "x": [3, 2, 1]}}
        right = {"a": {"x": [3, 2, 1], "y": 1}, "b": 2}

        self.assertEqual(canonical_json(left), '{"a":{"x":[3,2,1],"y":1},"b":2}')
        self.assertEqual(payload_sha256(left), payload_sha256(right))
        self.assertNotEqual(
            payload_sha256({"values": [1, 2]}),
            payload_sha256({"values": [2, 1]}),
        )

    def test_fetch_changed_response_shapes_raw_payload_and_headers(self) -> None:
        now = dt.datetime(2026, 6, 20, 21, 30, tzinfo=dt.UTC)
        opener = FakeOpener(
            FakeResponse(
                b'{"b": 2, "a": 1}',
                headers={
                    "ETag": '"new"',
                    "Last-Modified": "Sat, 20 Jun 2026 21:29:00 GMT",
                    "Content-Type": "application/json",
                },
            )
        )

        result = fetch_swpc_endpoint_json(
            {
                "path": "/products/noaa-scales.json",
                "family": "scales",
                "cadence_seconds": 60,
                "protection_tier": "minimal",
            },
            endpoint_state={
                "etag": '"old"',
                "last_modified": "Sat, 20 Jun 2026 21:28:00 GMT",
            },
            opener=opener,
            now=now,
            raw_uri_builder=lambda endpoint, fetched_at, hash_: (
                f"memory://{endpoint.strip('/')}/{fetched_at}/{hash_[:8]}"
            ),
        )

        request_headers = {
            key.lower(): value for key, value in opener.request.header_items()
        }
        expected_hash = payload_sha256({"a": 1, "b": 2})
        self.assertTrue(result.changed)
        self.assertEqual(
            opener.request.full_url,
            "https://services.swpc.noaa.gov/products/noaa-scales.json",
        )
        self.assertEqual(request_headers["if-none-match"], '"old"')
        self.assertEqual(
            request_headers["if-modified-since"],
            "Sat, 20 Jun 2026 21:28:00 GMT",
        )
        self.assertEqual(result.fetched_at, "2026-06-20T21:30:00Z")
        self.assertEqual(result.payload_hash, expected_hash)
        self.assertEqual(result.raw_payload_row["payload_hash"], expected_hash)
        self.assertEqual(result.raw_payload_row["payload_json"], {"a": 1, "b": 2})
        self.assertEqual(result.raw_payload_row["family"], "scales")
        self.assertEqual(result.raw_payload_row["protection_tier"], "minimal")
        self.assertEqual(result.raw_payload_row["cadence_seconds"], 60)
        self.assertEqual(result.endpoint_state_row["last_changed_at"], result.fetched_at)

    def test_fetch_unchanged_304_uses_cached_payload_hash(self) -> None:
        now = dt.datetime(2026, 6, 20, 21, 31, tzinfo=dt.UTC)
        error = HTTPError(
            "https://services.swpc.noaa.gov/products/noaa-scales.json",
            304,
            "Not Modified",
            {"ETag": '"same"'},
            None,
        )
        opener = FakeOpener(error=error)

        result = fetch_swpc_endpoint_json(
            "/products/noaa-scales.json",
            endpoint_state={"payload_hash": "a" * 64, "etag": '"old"'},
            opener=opener,
            now=now,
        )

        self.assertFalse(result.changed)
        self.assertIsNone(result.raw_payload_row)
        self.assertEqual(result.status_code, 304)
        self.assertEqual(result.payload_hash, "a" * 64)
        self.assertEqual(result.etag, '"same"')
        self.assertIsNone(result.endpoint_state_row["last_changed_at"])

    def test_fetch_invalid_json_returns_error_without_raw_row(self) -> None:
        opener = FakeOpener(
            FakeResponse(
                b"{not json",
                headers={"ETag": '"bad"', "Content-Type": "application/json"},
            )
        )

        result = fetch_swpc_endpoint_json(
            "/products/alerts.json",
            endpoint_state={"payload_hash": "b" * 64},
            opener=opener,
            now=dt.datetime(2026, 6, 20, 21, 32, tzinfo=dt.UTC),
        )

        self.assertFalse(result.changed)
        self.assertIsNone(result.raw_payload_row)
        self.assertEqual(result.payload_hash, "b" * 64)
        self.assertIsNotNone(result.error)
        self.assertTrue(result.error.startswith("invalid_json:"))
        self.assertEqual(result.endpoint_state_row["last_error"], result.error)

    def test_schema_setup_and_raw_upsert_are_idempotent_shapes(self) -> None:
        writer = FakeWriter()

        setup_swpc_schema(writer)
        self.assertEqual(writer.executed, list(SWPC_SCHEMA_STATEMENTS))
        self.assertIn(
            "CREATE TABLE IF NOT EXISTS swpc_raw_payloads",
            CREATE_SWPC_RAW_PAYLOADS_TABLE,
        )
        self.assertIn("UNIQUE (endpoint, payload_hash)", CREATE_SWPC_RAW_PAYLOADS_TABLE)
        self.assertIn(
            "CREATE TABLE IF NOT EXISTS swpc_forecast_records",
            CREATE_SWPC_FORECAST_RECORDS_TABLE,
        )
        self.assertIn("UNIQUE (record_hash)", CREATE_SWPC_FORECAST_RECORDS_TABLE)

        row = {
            "endpoint": "/products/noaa-scales.json",
            "payload_hash": "c" * 64,
            "payload_json": {"ok": True},
        }
        self.assertEqual(upsert_raw_payload_row(writer, row), [("ok",)])
        self.assertEqual(writer.upserts[0]["table"], "swpc_raw_payloads")
        self.assertEqual(
            writer.upserts[0]["conflict_columns"],
            ["endpoint", "payload_hash"],
        )
        self.assertEqual(
            writer.upserts[0]["update_columns"],
            RAW_PAYLOAD_UPDATE_COLUMNS,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
