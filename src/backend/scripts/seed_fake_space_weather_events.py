from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import secrets
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_SOURCE = "src/backend/scripts/seed_fake_space_weather_events.py"


def main() -> int:
    load_dotenv(BACKEND_ROOT / ".env")
    args = parse_args()
    now = dt.datetime.now(dt.UTC).replace(microsecond=0)
    rows = fake_event_rows(now, args)

    if args.dry_run:
        print(json.dumps(rows, indent=2, sort_keys=True))
        return 0

    data = upsert_rows(rows)
    print(
        json.dumps(
            [
                {
                    "id": row.get("id"),
                    "event_key": row.get("event_key"),
                    "event_type": row.get("event_type"),
                    "status": row.get("status"),
                    "peak_severity": row.get("peak_severity"),
                    "window_start": row.get("window_start"),
                    "window_end": row.get("window_end"),
                }
                for row in data
            ],
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Upsert fake severe solar-wind and geomagnetic-storm event windows "
            "into Supabase for local demos and Poller validation."
        )
    )
    parser.add_argument(
        "--start-offset-minutes",
        type=int,
        default=-5,
        help="Window start relative to now. Negative values make the events active.",
    )
    parser.add_argument(
        "--duration-hours",
        type=float,
        default=6.0,
        help="Event-window duration from the computed start time.",
    )
    parser.add_argument(
        "--key-prefix",
        default="soteria-fake-space-weather",
        help="Prefix used to derive event keys when --stable-keys is set.",
    )
    parser.add_argument(
        "--stable-keys",
        action="store_true",
        help="Use deterministic event keys so reruns update the same rows.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print rows without writing to Supabase.",
    )
    return parser.parse_args()


def fake_event_rows(now: dt.datetime, args: argparse.Namespace) -> list[dict[str, Any]]:
    start = now + dt.timedelta(minutes=args.start_offset_minutes)
    end = start + dt.timedelta(hours=args.duration_hours)
    peak = start + (end - start) / 2
    solar_event_key = make_event_key(args, "severe-solar-wind")
    geomagnetic_event_key = make_event_key(args, "severe-geomagnetic-storm")

    return [
        {
            "event_key": solar_event_key,
            "event_type": "solar_wind_coupling_risk",
            "source_product": "local_test_fake_event",
            "source_endpoint": SCRIPT_SOURCE,
            "window_start": iso_z(start),
            "peak_time": iso_z(peak),
            "window_end": iso_z(end),
            "peak_value": -24.0,
            "peak_severity": 5,
            "threshold_value": -5.0,
            "units": "nT",
            "confidence": "observed",
            "status": status_for(now, start, end),
            "evidence": {
                "fake": True,
                "source": SCRIPT_SOURCE,
                "scenario": "severe_solar_wind_coupling",
                "bz_gsm_nt": -24.0,
                "bt_nt": 36.0,
                "proton_speed_km_s": 820.0,
                "proton_density_cm3": 32.0,
                "note": "Synthetic severe solar-wind event for demos and validation.",
            },
            "updated_at": iso_z(now),
        },
        {
            "event_key": geomagnetic_event_key,
            "event_type": "geomagnetic_storm_risk",
            "source_product": "local_test_fake_event",
            "source_endpoint": SCRIPT_SOURCE,
            "window_start": iso_z(start),
            "peak_time": iso_z(peak),
            "window_end": iso_z(end),
            "peak_value": 8.0,
            "peak_severity": 4,
            "threshold_value": 5.0,
            "units": "Kp",
            "confidence": "forecast",
            "status": status_for(now, start, end),
            "evidence": {
                "fake": True,
                "source": SCRIPT_SOURCE,
                "scenario": "severe_geomagnetic_storm",
                "kp": 8.0,
                "noaa_scale": "G4",
                "note": "Synthetic severe geomagnetic storm event for demos and validation.",
            },
            "updated_at": iso_z(now),
        },
    ]


def make_event_key(args: argparse.Namespace, name: str) -> str:
    if args.stable_keys:
        return stable_event_key(args.key_prefix, name)
    return random_event_key()


def upsert_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if os.getenv("SUPABASE_DATABASE_URL"):
        return upsert_rows_with_supabase_cli(rows)
    return upsert_rows_with_data_api(rows)


def upsert_rows_with_supabase_cli(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    db_url = os.environ["SUPABASE_DATABASE_URL"]
    sql = upsert_sql(rows)
    sql_file = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".sql",
            prefix="soteria-fake-events-",
            delete=False,
        ) as handle:
            sql_file = Path(handle.name)
            handle.write(sql)

        result = subprocess.run(
            [
                "supabase",
                "db",
                "query",
                "--db-url",
                db_url,
                "--file",
                str(sql_file),
                "--output",
                "json",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    finally:
        if sql_file is not None:
            sql_file.unlink(missing_ok=True)

    if result.returncode != 0:
        raise RuntimeError(
            "supabase db query failed:\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{redact_secret(result.stderr, db_url)}"
        )
    output = json.loads(result.stdout or "[]")
    if isinstance(output, dict):
        return [dict(row) for row in output.get("rows", [])]
    return [dict(row) for row in output]


def upsert_sql(rows: list[dict[str, Any]]) -> str:
    payload = json.dumps(rows, separators=(",", ":"), sort_keys=True)
    tag = "$soteria_fake_events$"
    if tag in payload:
        raise ValueError("JSON payload contains the SQL dollar-quote tag.")
    return f"""
WITH payload AS (
    SELECT *
    FROM jsonb_to_recordset({tag}{payload}{tag}::jsonb) AS row(
        event_key TEXT,
        event_type TEXT,
        source_product TEXT,
        source_endpoint TEXT,
        window_start TIMESTAMPTZ,
        peak_time TIMESTAMPTZ,
        window_end TIMESTAMPTZ,
        peak_value DOUBLE PRECISION,
        peak_severity INTEGER,
        threshold_value DOUBLE PRECISION,
        units TEXT,
        confidence TEXT,
        status TEXT,
        evidence JSONB,
        updated_at TIMESTAMPTZ
    )
)
INSERT INTO public.space_weather_event_windows (
    event_key,
    event_type,
    source_product,
    source_endpoint,
    window_start,
    peak_time,
    window_end,
    peak_value,
    peak_severity,
    threshold_value,
    units,
    confidence,
    status,
    evidence,
    updated_at
)
SELECT
    event_key::char(64),
    event_type,
    source_product,
    source_endpoint,
    window_start,
    peak_time,
    window_end,
    peak_value,
    peak_severity,
    threshold_value,
    units,
    confidence,
    status,
    evidence,
    updated_at
FROM payload
ON CONFLICT (event_key) DO UPDATE SET
    event_type = EXCLUDED.event_type,
    source_product = EXCLUDED.source_product,
    source_endpoint = EXCLUDED.source_endpoint,
    window_start = EXCLUDED.window_start,
    peak_time = EXCLUDED.peak_time,
    window_end = EXCLUDED.window_end,
    peak_value = EXCLUDED.peak_value,
    peak_severity = EXCLUDED.peak_severity,
    threshold_value = EXCLUDED.threshold_value,
    units = EXCLUDED.units,
    confidence = EXCLUDED.confidence,
    status = EXCLUDED.status,
    evidence = EXCLUDED.evidence,
    updated_at = EXCLUDED.updated_at
RETURNING
    id,
    event_key,
    event_type,
    source_product,
    status,
    peak_severity,
    window_start,
    window_end;
"""


def upsert_rows_with_data_api(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    client = get_supabase_client()
    response = (
        client.table("space_weather_event_windows")
        .upsert(rows, on_conflict="event_key")
        .execute()
    )
    return [dict(row) for row in response.data or rows]


def redact_secret(text: str, secret: str) -> str:
    return text.replace(secret, "[redacted]")


def stable_event_key(prefix: str, name: str) -> str:
    return hashlib.sha256(f"{prefix}:{name}".encode("utf-8")).hexdigest()


def random_event_key() -> str:
    return secrets.token_hex(32)


def status_for(now: dt.datetime, start: dt.datetime, end: dt.datetime) -> str:
    if now < start:
        return "future"
    if now > end:
        return "ended"
    return "active"


def iso_z(value: dt.datetime) -> str:
    return value.astimezone(dt.UTC).isoformat().replace("+00:00", "Z")


def get_supabase_client() -> Any:
    from supabase import create_client

    url = os.getenv("SUPABASE_URL")
    key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
    )
    if not url or not key:
        raise RuntimeError(
            "Missing SUPABASE_URL and one of SUPABASE_SERVICE_ROLE_KEY, "
            "SUPABASE_KEY, or SUPABASE_ANON_KEY. The script also loads "
            "src/backend/.env when present."
        )
    return create_client(url, key)


if __name__ == "__main__":
    raise SystemExit(main())
