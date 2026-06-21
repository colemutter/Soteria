from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from typing import Any


Row = Mapping[str, Any]


class SupabaseSwpcWriter:
    """Supabase-backed writer for SWPC Airflow ingestion rows."""

    def __init__(
        self,
        *,
        url: str | None = None,
        key: str | None = None,
        chunk_size: int | None = None,
    ) -> None:
        self.url = (
            url or os.getenv("SUPABASE_URL") or _get_airflow_variable("SUPABASE_URL")
        )
        self.key = (
            key or os.getenv("SUPABASE_KEY") or _get_airflow_variable("SUPABASE_KEY")
        )
        self.chunk_size = chunk_size or int(os.getenv("SUPABASE_UPSERT_CHUNK_SIZE", "500"))
        if not self.url or not self.key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_KEY must be configured as environment "
                "variables or Airflow Variables"
            )
        self._client: Any | None = None

    @property
    def client(self) -> Any:
        if self._client is None:
            from supabase import create_client

            self._client = create_client(self.url, self.key)
        return self._client

    def get_endpoint_state(self, endpoint: str) -> dict[str, Any] | None:
        response = (
            self.client.table("swpc_endpoint_state")
            .select("endpoint,etag,last_modified,payload_hash,last_changed_at")
            .eq("endpoint", endpoint)
            .limit(1)
            .execute()
        )
        if not response.data:
            return None
        return dict(response.data[0])

    def upsert_endpoint_state(self, rows: Sequence[Row]) -> list[tuple[Any, ...]]:
        self._upsert("swpc_endpoint_state", rows, on_conflict="endpoint")
        return []

    def upsert_raw_payloads(
        self,
        rows: Sequence[Row],
        *,
        returning: Sequence[str] | str | None = None,
    ) -> list[tuple[Any, ...]]:
        data = self._upsert(
            "swpc_raw_payloads",
            rows,
            on_conflict="endpoint,payload_hash",
        )
        return self._returning(data, returning)

    def upsert_forecast_records(
        self,
        rows: Sequence[Row],
        *,
        returning: Sequence[str] | str | None = None,
    ) -> list[tuple[Any, ...]]:
        data = self._upsert(
            "swpc_forecast_records",
            rows,
            on_conflict="record_hash",
        )
        return self._returning(data, returning)

    def list_forecast_records(
        self,
        *,
        product_types: Sequence[str],
        valid_start_gte: str,
        limit: int = 50000,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        page_size = min(self.chunk_size, 1000)
        while len(rows) < limit:
            start = len(rows)
            end = min(start + page_size, limit) - 1
            response = (
                self.client.table("swpc_forecast_records")
                .select(
                    "id,endpoint,product_type,issued_at,valid_start,valid_end,"
                    "observed,severity,value,units,record,source,fetched_at"
                )
                .in_("product_type", list(product_types))
                .gte("valid_start", valid_start_gte)
                .order("valid_start")
                .range(start, end)
                .execute()
            )
            page = [dict(row) for row in response.data or []]
            rows.extend(page)
            if len(page) < page_size:
                break
        return rows

    def upsert_event_windows(
        self,
        rows: Sequence[Row],
        *,
        returning: Sequence[str] | str | None = None,
    ) -> list[tuple[Any, ...]]:
        data = self._upsert(
            "space_weather_event_windows",
            rows,
            on_conflict="event_key",
        )
        return self._returning(data, returning)

    def _upsert(
        self,
        table: str,
        rows: Sequence[Row],
        *,
        on_conflict: str,
    ) -> list[dict[str, Any]]:
        if not rows:
            return []

        returned: list[dict[str, Any]] = []
        for chunk in _chunks([dict(row) for row in rows], self.chunk_size):
            response = (
                self.client.table(table)
                .upsert(chunk, on_conflict=on_conflict)
                .execute()
            )
            if response.data:
                returned.extend(dict(row) for row in response.data)
        return returned

    def _returning(
        self,
        data: Sequence[Mapping[str, Any]],
        returning: Sequence[str] | str | None,
    ) -> list[tuple[Any, ...]]:
        if returning is None:
            return []
        columns = [returning] if isinstance(returning, str) else list(returning)
        return [tuple(row.get(column) for column in columns) for row in data]


def _chunks(rows: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [rows[index : index + size] for index in range(0, len(rows), size)]


def _get_airflow_variable(key: str) -> str | None:
    try:
        from airflow.sdk import Variable
    except ImportError:
        return None

    return Variable.get(key, default=None)


__all__ = ["SupabaseSwpcWriter"]
