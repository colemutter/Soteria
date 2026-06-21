from __future__ import annotations

import datetime as dt
import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PORT = 8077


def main() -> int:
    load_dotenv(BACKEND_ROOT / ".env")

    if os.getenv("RUN_LIVE_AGENT_PIPELINE_TESTS") != "true":
        print("Set RUN_LIVE_AGENT_PIPELINE_TESTS=true to run live validation.")
        return 2

    required = ["SUPABASE_URL", "CLAUDE_API_KEY"]
    missing = [name for name in required if not os.getenv(name)]
    if not (
        os.getenv("SUPABASE_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
    ):
        missing.append("SUPABASE_KEY or SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY")
    if missing:
        print("Missing required live validation env vars: " + ", ".join(missing))
        return 2

    port = int(os.getenv("LIVE_AGENT_PIPELINE_PORT", str(DEFAULT_PORT)))
    report_url = f"http://127.0.0.1:{port}/api/poller/report"
    started_at = dt.datetime.now(dt.UTC)
    child_env = live_validation_process_env()
    try:
        if not report_table_exists():
            print(
                "Live Supabase is missing public.satellite_event_reports. "
                "Apply supabase/migrations/20260621053000_create_satellite_event_reports.sql "
                "to the linked Supabase project, then rerun this validation.",
                file=sys.stderr,
            )
            return 2
        if not command_runbook_table_has_catalog_columns():
            print(
                "Live Supabase is missing catalog-backed command_runbooks columns. "
                "Apply supabase/migrations/20260621050000_create_command_runbooks.sql and "
                "supabase/migrations/20260621054500_extend_command_runbooks_catalog_metadata.sql "
                "to the linked Supabase project, then rerun this validation.",
                file=sys.stderr,
            )
            return 2
    except Exception as exc:
        if is_invalid_supabase_key_error(exc):
            print(
                "Supabase rejected the selected API key. "
                f"The live validation script selected {supabase_key_source()}. "
                "Set a valid SUPABASE_SERVICE_ROLE_KEY for this Supabase project, "
                "or unset stale SUPABASE_KEY/SUPABASE_ANON_KEY values in your shell.",
                file=sys.stderr,
            )
            return 2
        raise

    seed_fake_rows = env_flag("LIVE_POLLER_SEED_FAKE_ROWS", default=True)
    seeded_satellites: list[dict] = []
    seeded_event: dict | None = None
    if seed_fake_rows:
        seeded_satellites = seed_validation_satellites(started_at)
        seeded_event = seed_validation_event_window(started_at)
        print(
            "Seeded live validation satellites:",
            [
                {
                    "external_id": row.get("external_id"),
                    "name": row.get("name"),
                    "orbit_regime": row.get("orbit_regime"),
                    "operational_status": row.get("operational_status"),
                }
                for row in seeded_satellites
            ],
        )
        print(
            "Seeded live validation event window:",
            {
                "id": seeded_event.get("id"),
                "event_key": seeded_event.get("event_key"),
                "window_end": seeded_event.get("window_end"),
                "updated_at": seeded_event.get("updated_at"),
            },
        )

    print(
        "Starting local backend and live Poller. "
        "Rows in satellite_event_reports/command_runbooks appear after "
        "the Poller dispatches and the real report agent finishes.",
        flush=True,
    )
    backend = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=BACKEND_ROOT,
        env=child_env,
    )
    try:
        wait_for_backend(port)
        print(
            "Backend is ready. Running one live Poller cycle now; "
            "Poller output will stream below.",
            flush=True,
        )
        poller_env = child_env.copy()
        poller_env.update(
            {
                "PYTHONUNBUFFERED": "1",
                "SOTERIA_REACTION_SERVICE_URL": report_url,
                "LIVE_POLLER_TARGET_EVENT_WINDOW_ID": optional_str(seeded_event, "id") or "",
                "LIVE_POLLER_TARGET_UPDATED_AT": optional_str(seeded_event, "updated_at") or "",
                "LIVE_POLLER_LOOKBACK_MINUTES": os.getenv(
                    "LIVE_POLLER_LOOKBACK_MINUTES",
                    "30" if seed_fake_rows else "1440",
                ),
                "LIVE_POLLER_MAX_ROWS": os.getenv(
                    "LIVE_POLLER_MAX_ROWS",
                    "25" if seed_fake_rows else "5",
                ),
                "SOTERIA_REACTION_SERVICE_TIMEOUT_SECONDS": os.getenv(
                    "SOTERIA_REACTION_SERVICE_TIMEOUT_SECONDS",
                    "300",
                ),
            }
        )
        poller = subprocess.run(
            [
                sys.executable,
                "-u",
                "-c",
                POLLER_ONCE_CODE,
            ],
            cwd=BACKEND_ROOT,
            env=poller_env,
            text=True,
            timeout=int(os.getenv("LIVE_POLLER_TIMEOUT_SECONDS", "420")),
        )
        if poller.returncode != 0:
            return poller.returncode

        print(
            "Poller finished. Checking live Supabase for report and runbook rows.",
            flush=True,
        )
        report_rows = query_persisted_reports(
            started_at,
            event_window_id=optional_str(seeded_event, "id"),
        )
        if not report_rows:
            print(
                "Live Poller ran, but no satellite_event_reports rows were "
                "persisted for the seeded event window.",
                file=sys.stderr,
            )
            return 1

        print(f"Live validation persisted {len(report_rows)} satellite_event_reports row(s).")
        for row in report_rows[:5]:
            print(
                {
                    "id": row.get("id"),
                    "event_window_id": row.get("event_window_id"),
                    "status": row.get("status"),
                    "session_id": row.get("session_id"),
                    "created_at": row.get("created_at"),
                }
            )

        runbook_rows = query_persisted_runbooks(
            event_window_id=optional_str(seeded_event, "id"),
        )
        if not runbook_rows:
            print(
                "Report generation ran, but no command_runbooks rows were persisted "
                "for the seeded event window.",
                file=sys.stderr,
            )
            return 1

        seeded_external_ids = {
            str(row.get("external_id"))
            for row in seeded_satellites
            if row.get("external_id")
        }
        runbook_external_ids = {
            str(row.get("satellite_external_id"))
            for row in runbook_rows
            if row.get("satellite_external_id")
        }
        missing_seeded = sorted(seeded_external_ids - runbook_external_ids)
        if missing_seeded:
            print(
                "Missing command_runbooks rows for seeded satellites: "
                + ", ".join(missing_seeded),
                file=sys.stderr,
            )
            return 1

        print(f"Live validation persisted {len(runbook_rows)} command_runbooks row(s).")
        for row in runbook_rows[:20]:
            commands = row.get("commands") or []
            print(
                {
                    "satellite_external_id": row.get("satellite_external_id"),
                    "status": row.get("status"),
                    "risk_level": row.get("risk_level"),
                    "catalog_version": row.get("catalog_version"),
                    "policy_version": row.get("policy_version"),
                    "command_ids": [
                        command.get("catalog_command_id")
                        for command in commands
                        if isinstance(command, dict)
                    ],
                    "no_action_reason": (row.get("metadata") or {}).get(
                        "no_action_reason"
                    ),
                }
            )
        return 0
    finally:
        backend.terminate()
        try:
            backend.wait(timeout=10)
        except subprocess.TimeoutExpired:
            backend.kill()


def wait_for_backend(port: int) -> None:
    deadline = time.monotonic() + 30
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urlopen(f"http://127.0.0.1:{port}/docs", timeout=2) as response:
                if response.status < 500:
                    return
        except Exception as exc:
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError(f"Backend did not become ready: {last_error}")


def query_persisted_reports(
    started_at: dt.datetime,
    *,
    event_window_id: str | None,
) -> list[dict]:
    client = get_supabase_client()
    try:
        query = (
            client.table("satellite_event_reports")
            .select("id,event_window_id,status,session_id,created_at,report_json")
            .order("created_at", desc=True)
            .limit(20)
        )
        if event_window_id:
            query = query.eq("event_window_id", event_window_id)
        else:
            query = query.gte("created_at", started_at.isoformat().replace("+00:00", "Z"))
        response = query.execute()
    except Exception as exc:
        if is_missing_report_table_error(exc):
            raise RuntimeError(
                "Live Supabase is missing public.satellite_event_reports. "
                "Apply supabase/migrations/20260621053000_create_satellite_event_reports.sql."
            ) from exc
        raise
    return [dict(row) for row in response.data or []]


def query_persisted_runbooks(*, event_window_id: str | None) -> list[dict]:
    client = get_supabase_client()
    query = (
        client.table("command_runbooks")
        .select(
            "id,report_id,event_window_id,satellite_external_id,catalog_version,"
            "policy_version,commands,risk_level,status,source,metadata,created_at"
        )
        .order("created_at", desc=True)
        .limit(250)
    )
    if event_window_id:
        query = query.eq("event_window_id", event_window_id)
    response = query.execute()
    return [dict(row) for row in response.data or []]


def report_table_exists() -> bool:
    client = get_supabase_client()
    try:
        (
            client.table("satellite_event_reports")
            .select("id")
            .limit(1)
            .execute()
        )
    except Exception as exc:
        if is_missing_report_table_error(exc):
            return False
        raise
    return True


def command_runbook_table_has_catalog_columns() -> bool:
    client = get_supabase_client()
    try:
        (
            client.table("command_runbooks")
            .select("id,event_window_id,catalog_version,policy_version,evidence_hash,dedupe_key")
            .limit(1)
            .execute()
        )
    except Exception as exc:
        if is_missing_command_runbook_table_error(exc):
            return False
        raise
    return True


def seed_validation_satellites(now: dt.datetime) -> list[dict]:
    rows = [
        validation_satellite_row(
            external_id="soteria-live-cubesat-alpha",
            name="Soteria Live CubeSat Alpha",
            orbit_regime="LEO",
            now=now,
            altitude_km=410.0,
            mission_class="validation_payload",
        ),
        validation_satellite_row(
            external_id="soteria-live-cubesat-beta",
            name="Soteria Live CubeSat Beta",
            orbit_regime="LEO",
            now=now,
            altitude_km=525.0,
            mission_class="validation_adcs",
        ),
        validation_satellite_row(
            external_id="soteria-live-cubesat-gamma",
            name="Soteria Live CubeSat Gamma",
            orbit_regime="GEO",
            now=now,
            altitude_km=35786.0,
            mission_class="validation_comm",
        ),
    ]
    response = (
        get_supabase_client()
        .table("satellites")
        .upsert(rows, on_conflict="external_id")
        .execute()
    )
    return [dict(row) for row in response.data or rows]


def validation_satellite_row(
    *,
    external_id: str,
    name: str,
    orbit_regime: str,
    now: dt.datetime,
    altitude_km: float,
    mission_class: str,
) -> dict:
    return {
        "external_id": external_id,
        "norad_cat_id": None,
        "name": name,
        "operator": "Soteria live validation",
        "country": "US",
        "mission_class": mission_class,
        "operational_status": "active",
        "orbit_regime": orbit_regime,
        "tle_epoch": now.isoformat().replace("+00:00", "Z"),
        "reference_epoch": now.isoformat().replace("+00:00", "Z"),
        "mass_kg": 12.0,
        "cross_section_area_m2": 0.08,
        "drag_coefficient": 2.2,
        "ballistic_coefficient_kg_m2": 68.18,
        "position_time": now.isoformat().replace("+00:00", "Z"),
        "latitude_deg": 0.0,
        "longitude_deg": 0.0,
        "altitude_km": altitude_km,
        "speed_km_s": 7.6 if orbit_regime == "LEO" else 3.07,
        "updated_at": now.isoformat().replace("+00:00", "Z"),
    }


def seed_validation_event_window(now: dt.datetime) -> dict:
    client = get_supabase_client()
    if env_flag("LIVE_POLLER_STABLE_SEED_KEY", default=False):
        event_key = hashlib.sha256(b"soteria-live-validation-event-window").hexdigest()
    else:
        event_key = hashlib.sha256(
            f"soteria-live-validation:{now.isoformat()}".encode("utf-8")
        ).hexdigest()
    row = {
        "event_key": event_key,
        "event_type": "geomagnetic_storm_risk",
        "source_product": "soteria_live_validation",
        "source_endpoint": "src/backend/scripts/live_poller_report_validation.py",
        "window_start": (now - dt.timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
        "peak_time": now.isoformat().replace("+00:00", "Z"),
        "window_end": (now + dt.timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
        "peak_value": 7.0,
        "peak_severity": 3,
        "threshold_value": 5.0,
        "units": "Kp",
        "confidence": "forecast",
        "status": "active",
        "evidence": {
            "validation": True,
            "source": "live_poller_report_validation.py",
            "note": "Synthetic live-validation event window for local Poller pipeline test.",
        },
        "updated_at": now.isoformat().replace("+00:00", "Z"),
    }
    response = (
        client.table("space_weather_event_windows")
        .upsert(row, on_conflict="event_key")
        .execute()
    )
    data = response.data or []
    return dict(data[0]) if data else row


def get_supabase_client():
    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    key = selected_supabase_key()
    return create_client(url, key)


def selected_supabase_key() -> str:
    key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
    )
    if not key:
        raise RuntimeError(
            "Missing SUPABASE_SERVICE_ROLE_KEY, SUPABASE_KEY, or SUPABASE_ANON_KEY."
        )
    return key


def live_validation_process_env() -> dict[str, str]:
    """Normalize child process Supabase auth to the key that passed preflight."""
    env = os.environ.copy()
    key = selected_supabase_key()
    env["SUPABASE_KEY"] = key
    env["SUPABASE_SERVICE_ROLE_KEY"] = key
    return env


def supabase_key_source() -> str:
    for name in ("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_KEY", "SUPABASE_ANON_KEY"):
        if os.getenv(name):
            return name
    return "<none>"


def env_flag(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes"}


def optional_str(row: dict | None, key: str) -> str | None:
    if row is None:
        return None
    value = row.get(key)
    if value is None:
        return None
    return str(value)


def is_missing_report_table_error(exc: Exception) -> bool:
    text = str(exc)
    return (
        "PGRST205" in text
        or "satellite_event_reports" in text
        and "schema cache" in text
    )


def is_missing_command_runbook_table_error(exc: Exception) -> bool:
    text = str(exc)
    return (
        "PGRST205" in text
        or "command_runbooks" in text
        and "schema cache" in text
    )


def is_invalid_supabase_key_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "invalid api key" in text or "supabase" in text and "401" in text


POLLER_ONCE_CODE = r"""
import asyncio
import datetime as dt
import os

from api.poller import EventWindowPoller, EventWindowPollerSettings, configure_logging


def _parse_utc(value):
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


async def run_once():
    configure_logging()
    poller = EventWindowPoller(
        settings=EventWindowPollerSettings(
            initial_lookback_minutes=int(os.getenv("LIVE_POLLER_LOOKBACK_MINUTES", "1440")),
            max_rows_per_poll=int(os.getenv("LIVE_POLLER_MAX_ROWS", "5")),
            min_peak_severity=int(os.getenv("LIVE_POLLER_MIN_SEVERITY", "0")),
            include_ended_windows=os.getenv("LIVE_POLLER_INCLUDE_ENDED", "true").lower()
            in {"1", "true", "yes"},
            poll_interval_seconds=1,
        )
    )
    target_updated_at = os.getenv("LIVE_POLLER_TARGET_UPDATED_AT", "").strip()
    if target_updated_at:
        target_time = _parse_utc(target_updated_at)
        poller._watermark = target_time - dt.timedelta(microseconds=1)
    target_event_window_id = os.getenv("LIVE_POLLER_TARGET_EVENT_WINDOW_ID", "").strip()
    if target_event_window_id:
        original_query_changed_event_windows = poller._query_changed_event_windows

        def query_target_event_window_only():
            return [
                row
                for row in original_query_changed_event_windows()
                if str(row.get("id")) == target_event_window_id
            ]

        poller._query_changed_event_windows = query_target_event_window_only
    try:
        print(
            {
                "poller_lookback_minutes": poller.settings.initial_lookback_minutes,
                "poller_max_rows": poller.settings.max_rows_per_poll,
                "poller_watermark": poller._watermark.isoformat(),
                "target_event_window_id": target_event_window_id or None,
            },
            flush=True,
        )
        rows = poller._query_changed_event_windows()
        print({"queried_event_window_count": len(rows)}, flush=True)
        for row in rows:
            message = __import__("api.poller", fromlist=["_reaction_message"])._reaction_message(row)
            if message is None:
                print({"event_window_id": row.get("id"), "skip_reason": "invalid_reaction_message"}, flush=True)
                continue
            should_dispatch, reason = poller._dispatch_decision(message)
            print(
                {
                    "event_window_id": message.event_window_id,
                    "status": message.status,
                    "window_end": message.window_end.isoformat(),
                    "peak_severity": message.peak_severity,
                    "dispatch_decision": reason if not should_dispatch else "eligible",
                },
                flush=True,
            )
        print(
            {
                "poller_dispatch_start": True,
                "note": (
                    "If output pauses here, /api/poller/report is running the "
                    "real report agent and writing Supabase rows."
                ),
            },
            flush=True,
        )
        messages = await poller.poll_once()
        print({"dispatched_event_window_ids": [message.event_window_id for message in messages]}, flush=True)
        if not messages:
            raise RuntimeError(
                "Poller found no eligible event windows. The rows above show skip reasons. "
                "By default this script seeds a clearly marked future live-validation "
                "event window; check Supabase credentials, schema, and Poller filters."
            )
    finally:
        await poller.close()


asyncio.run(run_once())
"""


if __name__ == "__main__":
    raise SystemExit(main())
