from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class SchemaWriter(Protocol):
    def execute(
        self,
        query: str,
        params: Sequence[object] = (),
    ) -> None: ...


CREATE_SWPC_RAW_PAYLOADS_TABLE = """
CREATE TABLE IF NOT EXISTS swpc_raw_payloads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    endpoint TEXT NOT NULL,
    family TEXT,
    protection_tier TEXT,
    cadence_seconds INTEGER,
    source_url TEXT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL,
    response_status INTEGER NOT NULL,
    etag TEXT,
    last_modified TEXT,
    content_type TEXT,
    payload_hash CHAR(64) NOT NULL,
    payload_json JSONB NOT NULL,
    raw_uri TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT swpc_raw_payloads_endpoint_payload_hash_key
        UNIQUE (endpoint, payload_hash),
    CONSTRAINT swpc_raw_payloads_payload_hash_hex
        CHECK (payload_hash ~ '^[0-9a-f]{64}$')
)
"""

CREATE_SWPC_RAW_PAYLOADS_ENDPOINT_FETCHED_INDEX = """
CREATE INDEX IF NOT EXISTS swpc_raw_payloads_endpoint_fetched_at_idx
    ON swpc_raw_payloads (endpoint, fetched_at DESC)
"""

CREATE_SWPC_RAW_PAYLOADS_HASH_INDEX = """
CREATE INDEX IF NOT EXISTS swpc_raw_payloads_payload_hash_idx
    ON swpc_raw_payloads (payload_hash)
"""

CREATE_SWPC_FORECAST_RECORDS_TABLE = """
CREATE TABLE IF NOT EXISTS swpc_forecast_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    endpoint TEXT NOT NULL,
    record_hash CHAR(64) NOT NULL,
    product_type TEXT NOT NULL,
    issued_at TIMESTAMPTZ,
    valid_start TIMESTAMPTZ,
    valid_end TIMESTAMPTZ,
    observed BOOLEAN,
    severity INTEGER,
    value DOUBLE PRECISION,
    units TEXT,
    record JSONB NOT NULL,
    raw_payload_id UUID REFERENCES swpc_raw_payloads(id) ON DELETE SET NULL,
    source TEXT,
    fetched_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT swpc_forecast_records_record_hash_key UNIQUE (record_hash),
    CONSTRAINT swpc_forecast_records_record_hash_hex
        CHECK (record_hash ~ '^[0-9a-f]{64}$')
)
"""

CREATE_SWPC_FORECAST_RECORDS_ENDPOINT_VALID_INDEX = """
CREATE INDEX IF NOT EXISTS swpc_forecast_records_endpoint_valid_idx
    ON swpc_forecast_records (endpoint, valid_start DESC)
"""

CREATE_SWPC_FORECAST_RECORDS_SCALE_INDEX = """
CREATE INDEX IF NOT EXISTS swpc_forecast_records_scale_idx
    ON swpc_forecast_records (product_type, severity)
    WHERE severity IS NOT NULL
"""

CREATE_SWPC_ENDPOINT_STATE_TABLE = """
CREATE TABLE IF NOT EXISTS swpc_endpoint_state (
    endpoint TEXT PRIMARY KEY,
    etag TEXT,
    last_modified TEXT,
    payload_hash CHAR(64),
    last_fetched_at TIMESTAMPTZ,
    last_changed_at TIMESTAMPTZ,
    last_status_code INTEGER,
    last_error TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT swpc_endpoint_state_payload_hash_hex
        CHECK (
            payload_hash IS NULL
            OR payload_hash ~ '^[0-9a-f]{64}$'
        )
)
"""

SWPC_SCHEMA_STATEMENTS = (
    "CREATE EXTENSION IF NOT EXISTS pgcrypto",
    CREATE_SWPC_RAW_PAYLOADS_TABLE,
    CREATE_SWPC_RAW_PAYLOADS_ENDPOINT_FETCHED_INDEX,
    CREATE_SWPC_RAW_PAYLOADS_HASH_INDEX,
    CREATE_SWPC_FORECAST_RECORDS_TABLE,
    CREATE_SWPC_FORECAST_RECORDS_ENDPOINT_VALID_INDEX,
    CREATE_SWPC_FORECAST_RECORDS_SCALE_INDEX,
    CREATE_SWPC_ENDPOINT_STATE_TABLE,
)


def setup_swpc_schema(writer: SchemaWriter) -> None:
    """Create SWPC raw payload and forecast record tables if they are missing."""

    for statement in SWPC_SCHEMA_STATEMENTS:
        writer.execute(statement)


__all__ = [
    "CREATE_SWPC_FORECAST_RECORDS_TABLE",
    "CREATE_SWPC_ENDPOINT_STATE_TABLE",
    "CREATE_SWPC_RAW_PAYLOADS_TABLE",
    "SWPC_SCHEMA_STATEMENTS",
    "setup_swpc_schema",
]
