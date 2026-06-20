from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


Row = Mapping[str, Any]


@dataclass(frozen=True)
class NeonConnectionConfig:
    """Connection settings for a Neon-backed Airflow ETL writer."""

    database_url: str | None = None
    database_url_env: str = "NEON_DATABASE_URL"
    airflow_conn_id: str | None = "warehouse"
    neon_project_id: str | None = None
    neon_database_name: str | None = None
    neon_role_name: str | None = None
    neon_pooled: bool = True


class NeonDbWriter:
    """Small Postgres writer for Airflow tasks that target a Neon database.

    The Neon Python SDK (`neon_api`) manages Neon resources and can return a
    connection URI. Row-level inserts still go through a Postgres driver, so
    this class uses `psycopg` for inserts/upserts once it has a database URL.
    """

    def __init__(self, config: NeonConnectionConfig | None = None) -> None:
        self.config = config or NeonConnectionConfig()

    @classmethod
    def from_database_url(cls, database_url: str) -> NeonDbWriter:
        return cls(NeonConnectionConfig(database_url=database_url))

    @classmethod
    def from_env(cls, env_var: str = "NEON_DATABASE_URL") -> NeonDbWriter:
        return cls(NeonConnectionConfig(database_url_env=env_var, airflow_conn_id=None))

    @classmethod
    def from_airflow_connection(cls, conn_id: str = "warehouse") -> NeonDbWriter:
        return cls(NeonConnectionConfig(airflow_conn_id=conn_id))

    @classmethod
    def from_neon_api(
        cls,
        *,
        project_id: str,
        database_name: str | None = None,
        role_name: str | None = None,
        pooled: bool = True,
    ) -> NeonDbWriter:
        return cls(
            NeonConnectionConfig(
                airflow_conn_id=None,
                neon_project_id=project_id,
                neon_database_name=database_name,
                neon_role_name=role_name,
                neon_pooled=pooled,
            )
        )

    def resolve_database_url(self) -> str:
        if self.config.database_url:
            return self.config.database_url

        if self.config.airflow_conn_id:
            database_url = self._database_url_from_airflow_connection(
                self.config.airflow_conn_id
            )
            if database_url:
                return database_url

        database_url = os.getenv(self.config.database_url_env)
        if database_url:
            return database_url

        if self.config.neon_project_id:
            return self._database_url_from_neon_api()

        raise RuntimeError(
            "No Neon database URL configured. Set an Airflow connection, "
            f"{self.config.database_url_env}, pass database_url, or configure "
            "Neon API project settings."
        )

    def execute(
        self,
        query: str,
        params: Sequence[Any] | Mapping[str, Any] = (),
    ) -> None:
        import psycopg

        with psycopg.connect(self.resolve_database_url()) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
            connection.commit()

    def fetch_one(
        self,
        query: str,
        params: Sequence[Any] | Mapping[str, Any] = (),
    ) -> tuple[Any, ...] | None:
        import psycopg

        with psycopg.connect(self.resolve_database_url()) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                return cursor.fetchone()

    def fetch_all(
        self,
        query: str,
        params: Sequence[Any] | Mapping[str, Any] = (),
    ) -> list[tuple[Any, ...]]:
        import psycopg

        with psycopg.connect(self.resolve_database_url()) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                return list(cursor.fetchall())

    def insert_rows(
        self,
        table: str,
        rows: Sequence[Row],
        *,
        returning: Sequence[str] | str | None = None,
    ) -> list[tuple[Any, ...]]:
        if not rows:
            return []

        statement, values = self._build_insert(table, rows, returning=returning)
        return self._execute_many(statement, values, fetch=returning is not None)

    def upsert_rows(
        self,
        table: str,
        rows: Sequence[Row],
        *,
        conflict_columns: Sequence[str],
        update_columns: Sequence[str] | None = None,
        returning: Sequence[str] | str | None = None,
    ) -> list[tuple[Any, ...]]:
        if not rows:
            return []
        if not conflict_columns:
            raise ValueError("conflict_columns must contain at least one column")

        first_row_columns = list(rows[0].keys())
        update_columns = list(update_columns or first_row_columns)
        update_columns = [
            column for column in update_columns if column not in set(conflict_columns)
        ]

        statement, values = self._build_insert(table, rows, returning=None)
        statement += " ON CONFLICT ({conflict_columns}) ".format(
            conflict_columns=", ".join(
                self._quote_identifier(column) for column in conflict_columns
            )
        )

        if update_columns:
            assignments = ", ".join(
                (
                    f"{self._quote_identifier(column)} = "
                    f"EXCLUDED.{self._quote_identifier(column)}"
                )
                for column in update_columns
            )
            statement += f"DO UPDATE SET {assignments}"
        else:
            statement += "DO NOTHING"

        if returning:
            statement += f" RETURNING {self._format_returning(returning)}"

        return self._execute_many(statement, values, fetch=returning is not None)

    def upsert_endpoint_state(self, rows: Sequence[Row]) -> list[tuple[Any, ...]]:
        return self.upsert_rows(
            "swpc_endpoint_state",
            rows,
            conflict_columns=["endpoint"],
        )

    def get_endpoint_state(self, endpoint: str) -> dict[str, Any] | None:
        row = self.fetch_one(
            """
            SELECT endpoint, etag, last_modified, payload_hash, last_changed_at
            FROM swpc_endpoint_state
            WHERE endpoint = %s
            """,
            (endpoint,),
        )
        if row is None:
            return None
        return {
            "endpoint": row[0],
            "etag": row[1],
            "last_modified": row[2],
            "payload_hash": row[3],
            "last_changed_at": row[4],
        }

    def upsert_raw_payloads(
        self,
        rows: Sequence[Row],
        *,
        returning: Sequence[str] | str | None = None,
    ) -> list[tuple[Any, ...]]:
        return self.upsert_rows(
            "swpc_raw_payloads",
            rows,
            conflict_columns=["endpoint", "payload_hash"],
            update_columns=[
                "fetched_at",
                "response_status",
                "etag",
                "last_modified",
                "content_type",
                "raw_uri",
            ],
            returning=returning,
        )

    def upsert_forecast_records(
        self,
        rows: Sequence[Row],
        *,
        returning: Sequence[str] | str | None = None,
    ) -> list[tuple[Any, ...]]:
        return self.upsert_rows(
            "swpc_forecast_records",
            rows,
            conflict_columns=["record_hash"],
            update_columns=[
                "raw_payload_id",
                "source",
                "fetched_at",
                "record",
            ],
            returning=returning,
        )

    def upsert_current_state(self, rows: Sequence[Row]) -> list[tuple[Any, ...]]:
        return self.upsert_rows(
            "swpc_current_state",
            rows,
            conflict_columns=["key"],
        )

    def insert_scale_events(
        self,
        rows: Sequence[Row],
        *,
        returning: Sequence[str] | str | None = None,
    ) -> list[tuple[Any, ...]]:
        return self.insert_rows("swpc_scale_events", rows, returning=returning)

    def _execute_many(
        self,
        statement: str,
        values: Sequence[Sequence[Any]],
        *,
        fetch: bool,
    ) -> list[tuple[Any, ...]]:
        import psycopg

        results: list[tuple[Any, ...]] = []
        with psycopg.connect(self.resolve_database_url()) as connection:
            with connection.cursor() as cursor:
                for value_set in values:
                    cursor.execute(statement, value_set)
                    if fetch:
                        results.extend(cursor.fetchall())
            connection.commit()
        return results

    def _build_insert(
        self,
        table: str,
        rows: Sequence[Row],
        *,
        returning: Sequence[str] | str | None,
    ) -> tuple[str, list[tuple[Any, ...]]]:
        columns = list(rows[0].keys())
        if not columns:
            raise ValueError("rows must contain at least one column")

        for row in rows:
            if list(row.keys()) != columns:
                raise ValueError("all rows must have the same columns in the same order")

        quoted_columns = ", ".join(self._quote_identifier(column) for column in columns)
        placeholders = ", ".join(["%s"] * len(columns))
        statement = (
            f"INSERT INTO {self._quote_table(table)} ({quoted_columns}) "
            f"VALUES ({placeholders})"
        )
        if returning:
            statement += f" RETURNING {self._format_returning(returning)}"

        values = [
            tuple(self._adapt_value(row[column]) for column in columns) for row in rows
        ]
        return statement, values

    def _database_url_from_airflow_connection(self, conn_id: str) -> str | None:
        try:
            from airflow.hooks.base import BaseHook
        except ImportError:
            return None

        try:
            connection = BaseHook.get_connection(conn_id)
        except Exception as exc:
            if exc.__class__.__name__ == "AirflowNotFoundException":
                return None
            raise

        uri = connection.get_uri()
        if uri.startswith("postgres://"):
            return uri.replace("postgres://", "postgresql://", 1)
        return uri

    def _database_url_from_neon_api(self) -> str:
        from neon_api import NeonAPI

        if not self.config.neon_project_id:
            raise RuntimeError("neon_project_id is required for Neon API URI lookup")

        neon = NeonAPI.from_environ()
        response = neon.connection_uri(
            project_id=self.config.neon_project_id,
            database_name=self.config.neon_database_name,
            role_name=self.config.neon_role_name,
            pooled=self.config.neon_pooled,
        )
        if isinstance(response, str):
            return response
        if isinstance(response, Mapping):
            return str(response["connection_uri"])
        return response.connection_uri

    def _adapt_value(self, value: Any) -> Any:
        if isinstance(value, Mapping) or isinstance(value, list):
            from psycopg.types.json import Jsonb

            return Jsonb(value)
        return value

    def _format_returning(self, returning: Sequence[str] | str) -> str:
        if isinstance(returning, str):
            returning = [returning]
        return ", ".join(
            "*" if column == "*" else self._quote_identifier(column)
            for column in returning
        )

    def _quote_table(self, table: str) -> str:
        return ".".join(self._quote_identifier(part) for part in table.split("."))

    def _quote_identifier(self, identifier: str) -> str:
        if not identifier:
            raise ValueError("identifier cannot be empty")
        return '"' + identifier.replace('"', '""') + '"'
