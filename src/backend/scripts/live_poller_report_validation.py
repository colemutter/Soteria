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
    if not report_table_exists():
        print(
            "Live Supabase is missing public.satellite_event_reports. "
            "Apply supabase/migrations/20260621053000_create_satellite_event_reports.sql "
            "to the linked Supabase project, then rerun this validation.",
            file=sys.stderr,
        )
        return 2

    seed_event_window = env_flag("LIVE_POLLER_SEED_EVENT_WINDOW")
    if seed_event_window:
        seeded = seed_validation_event_window(started_at)
        print(
            "Seeded live validation event window:",
            {
                "id": seeded.get("id"),
                "event_key": seeded.get("event_key"),
                "window_end": seeded.get("window_end"),
                "updated_at": seeded.get("updated_at"),
            },
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
        env=os.environ.copy(),
    )
    try:
        wait_for_backend(port)
        poller_env = os.environ.copy()
        poller_env.update(
            {
                "SOTERIA_REACTION_SERVICE_URL": report_url,
                "LIVE_POLLER_LOOKBACK_MINUTES": os.getenv(
                    "LIVE_POLLER_LOOKBACK_MINUTES",
                    "30" if seed_event_window else "1440",
                ),
                "LIVE_POLLER_MAX_ROWS": os.getenv(
                    "LIVE_POLLER_MAX_ROWS",
                    "25" if seed_event_window else "5",
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
                "-c",
                POLLER_ONCE_CODE,
            ],
            cwd=BACKEND_ROOT,
            env=poller_env,
            text=True,
            capture_output=True,
            timeout=int(os.getenv("LIVE_POLLER_TIMEOUT_SECONDS", "420")),
        )
        print(poller.stdout)
        if poller.returncode != 0:
            print(poller.stderr, file=sys.stderr)
            return poller.returncode

        rows = query_persisted_reports(started_at)
        if not rows:
            print(
                "Live Poller ran, but no satellite_event_reports rows were "
                "persisted after the validation start time.",
                file=sys.stderr,
            )
            return 1

        print(f"Live validation persisted {len(rows)} satellite_event_reports row(s).")
        for row in rows[:5]:
            print(
                {
                    "event_window_id": row.get("event_window_id"),
                    "status": row.get("status"),
                    "session_id": row.get("session_id"),
                    "created_at": row.get("created_at"),
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


def query_persisted_reports(started_at: dt.datetime) -> list[dict]:
    client = get_supabase_client()
    try:
        response = (
            client.table("satellite_event_reports")
            .select("event_window_id,status,session_id,created_at")
            .gte("created_at", started_at.isoformat().replace("+00:00", "Z"))
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
    except Exception as exc:
        if is_missing_report_table_error(exc):
            raise RuntimeError(
                "Live Supabase is missing public.satellite_event_reports. "
                "Apply supabase/migrations/20260621053000_create_satellite_event_reports.sql."
            ) from exc
        raise
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


def seed_validation_event_window(now: dt.datetime) -> dict:
    client = get_supabase_client()
    event_key = hashlib.sha256(b"soteria-live-validation-event-window").hexdigest()
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
    key = (
        os.getenv("SUPABASE_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
    )
    return create_client(url, key)


def env_flag(name: str) -> bool:
    return os.getenv(name, "").lower() in {"1", "true", "yes"}


def is_missing_report_table_error(exc: Exception) -> bool:
    text = str(exc)
    return (
        "PGRST205" in text
        or "satellite_event_reports" in text
        and "schema cache" in text
    )


POLLER_ONCE_CODE = r"""
import asyncio
import os

from api.poller import EventWindowPoller, EventWindowPollerSettings, configure_logging


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
    try:
        print(
            {
                "poller_lookback_minutes": poller.settings.initial_lookback_minutes,
                "poller_max_rows": poller.settings.max_rows_per_poll,
                "poller_watermark": poller._watermark.isoformat(),
            }
        )
        rows = poller._query_changed_event_windows()
        print({"queried_event_window_count": len(rows)})
        for row in rows:
            message = __import__("api.poller", fromlist=["_reaction_message"])._reaction_message(row)
            if message is None:
                print({"event_window_id": row.get("id"), "skip_reason": "invalid_reaction_message"})
                continue
            should_dispatch, reason = poller._dispatch_decision(message)
            print(
                {
                    "event_window_id": message.event_window_id,
                    "status": message.status,
                    "window_end": message.window_end.isoformat(),
                    "peak_severity": message.peak_severity,
                    "dispatch_decision": reason if not should_dispatch else "eligible",
                }
            )
        messages = await poller.poll_once()
        print({"dispatched_event_window_ids": [message.event_window_id for message in messages]})
        if not messages:
            raise RuntimeError(
                "Poller found no eligible event windows. The rows above show skip reasons. "
                "If they are expired, rerun with LIVE_POLLER_SEED_EVENT_WINDOW=true to "
                "upsert a clearly marked future live-validation event window."
            )
    finally:
        await poller.close()


asyncio.run(run_once())
"""


if __name__ == "__main__":
    raise SystemExit(main())
