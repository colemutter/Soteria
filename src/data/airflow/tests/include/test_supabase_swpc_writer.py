from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch


AIRFLOW_ROOT = Path(__file__).resolve().parents[2]
if str(AIRFLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(AIRFLOW_ROOT))

from include.supabase_swpc_writer import SupabaseSwpcWriter  # noqa: E402


class FakeResponse:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class FakeQuery:
    def __init__(self, table: "FakeTable") -> None:
        self.table = table

    def select(self, columns: str) -> "FakeQuery":
        self.table.calls.append(("select", columns))
        return self

    def eq(self, column: str, value: Any) -> "FakeQuery":
        self.table.calls.append(("eq", column, value))
        return self

    def in_(self, column: str, values: list[Any]) -> "FakeQuery":
        self.table.calls.append(("in_", column, values))
        return self

    def gte(self, column: str, value: Any) -> "FakeQuery":
        self.table.calls.append(("gte", column, value))
        return self

    def order(self, column: str) -> "FakeQuery":
        self.table.calls.append(("order", column))
        return self

    def limit(self, value: int) -> "FakeQuery":
        self.table.calls.append(("limit", value))
        return self

    def range(self, start: int, end: int) -> "FakeQuery":
        self.table.calls.append(("range", start, end))
        return self

    def upsert(self, rows: list[dict[str, Any]], *, on_conflict: str) -> "FakeQuery":
        self.table.calls.append(("upsert", rows, on_conflict))
        self.table.pending_response = rows
        return self

    def execute(self) -> FakeResponse:
        return FakeResponse(self.table.pending_response)


class FakeTable:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[tuple[Any, ...]] = []
        self.pending_response: list[dict[str, Any]] = []

    def select(self, columns: str) -> FakeQuery:
        return FakeQuery(self).select(columns)

    def upsert(self, rows: list[dict[str, Any]], *, on_conflict: str) -> FakeQuery:
        return FakeQuery(self).upsert(rows, on_conflict=on_conflict)


class FakeClient:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {}

    def table(self, name: str) -> FakeTable:
        self.tables.setdefault(name, FakeTable(name))
        return self.tables[name]


class TestSupabaseSwpcWriter(unittest.TestCase):
    def writer_with_client(self, client: FakeClient) -> SupabaseSwpcWriter:
        writer = SupabaseSwpcWriter(url="https://example.supabase.co", key="test", chunk_size=2)
        writer._client = client
        return writer

    def test_reads_supabase_config_from_airflow_variables_when_env_is_unset(self) -> None:
        variables = {
            "SUPABASE_URL": "https://variables.supabase.co",
            "SUPABASE_KEY": "variable-key",
        }

        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "include.supabase_swpc_writer._get_airflow_variable",
                side_effect=lambda key: variables.get(key),
            ),
        ):
            writer = SupabaseSwpcWriter()

        self.assertEqual(writer.url, "https://variables.supabase.co")
        self.assertEqual(writer.key, "variable-key")

    def test_env_supabase_config_takes_precedence_over_airflow_variables(self) -> None:
        variables = {
            "SUPABASE_URL": "https://variables.supabase.co",
            "SUPABASE_KEY": "variable-key",
        }

        with (
            patch.dict(
                os.environ,
                {
                    "SUPABASE_URL": "https://env.supabase.co",
                    "SUPABASE_KEY": "env-key",
                },
                clear=True,
            ),
            patch(
                "include.supabase_swpc_writer._get_airflow_variable",
                side_effect=lambda key: variables.get(key),
            ),
        ):
            writer = SupabaseSwpcWriter()

        self.assertEqual(writer.url, "https://env.supabase.co")
        self.assertEqual(writer.key, "env-key")

    def test_missing_supabase_config_raises_runtime_error(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("include.supabase_swpc_writer._get_airflow_variable", return_value=None),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "SUPABASE_URL and SUPABASE_KEY must be configured as environment "
                "variables or Airflow Variables",
            ):
                SupabaseSwpcWriter()

    def test_raw_payload_upsert_returns_requested_id(self) -> None:
        client = FakeClient()
        writer = self.writer_with_client(client)

        rows = [{"id": "raw-1", "endpoint": "/x", "payload_hash": "a" * 64}]
        returned = writer.upsert_raw_payloads(rows, returning="id")

        self.assertEqual(returned, [("raw-1",)])
        self.assertIn(
            ("upsert", rows, "endpoint,payload_hash"),
            client.tables["swpc_raw_payloads"].calls,
        )

    def test_forecast_upsert_uses_record_hash_conflict(self) -> None:
        client = FakeClient()
        writer = self.writer_with_client(client)

        rows = [{"record_hash": "b" * 64, "endpoint": "/x"}]
        writer.upsert_forecast_records(rows)

        self.assertIn(
            ("upsert", rows, "record_hash"),
            client.tables["swpc_forecast_records"].calls,
        )

    def test_endpoint_state_upsert_uses_endpoint_conflict(self) -> None:
        client = FakeClient()
        writer = self.writer_with_client(client)

        rows = [{"endpoint": "/x", "etag": "abc"}]
        writer.upsert_endpoint_state(rows)

        self.assertIn(
            ("upsert", rows, "endpoint"),
            client.tables["swpc_endpoint_state"].calls,
        )

    def test_event_window_upsert_uses_event_key_conflict(self) -> None:
        client = FakeClient()
        writer = self.writer_with_client(client)

        rows = [{"event_key": "c" * 64, "event_type": "geomagnetic_storm_risk"}]
        writer.upsert_event_windows(rows)

        self.assertIn(
            ("upsert", rows, "event_key"),
            client.tables["space_weather_event_windows"].calls,
        )

    def test_list_forecast_records_filters_by_products_and_start_time(self) -> None:
        client = FakeClient()
        table = client.table("swpc_forecast_records")
        table.pending_response = [{"id": "r1", "product_type": "kp_forecast"}]
        writer = self.writer_with_client(client)

        rows = writer.list_forecast_records(
            product_types=("kp_forecast", "noaa_scale_g"),
            valid_start_gte="2026-06-20T00:00:00Z",
            limit=10,
        )

        self.assertEqual(rows, [{"id": "r1", "product_type": "kp_forecast"}])
        self.assertIn(
            ("in_", "product_type", ["kp_forecast", "noaa_scale_g"]),
            table.calls,
        )
        self.assertIn(("gte", "valid_start", "2026-06-20T00:00:00Z"), table.calls)
        self.assertIn(("order", "valid_start"), table.calls)
        self.assertIn(("range", 0, 1), table.calls)


if __name__ == "__main__":
    unittest.main(verbosity=2)
