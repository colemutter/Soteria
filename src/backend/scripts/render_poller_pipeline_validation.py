from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_RENDER_BACKEND_URL = "https://soteria-backend-7360.onrender.com"


def main() -> int:
    if os.getenv("RUN_RENDER_PIPELINE_TESTS") != "true":
        print("Set RUN_RENDER_PIPELINE_TESTS=true to run Render pipeline validation.")
        return 2

    parser = argparse.ArgumentParser(
        description=(
            "Seed linked Supabase validation data, then wait for the deployed "
            "Render poller/backend pipeline to persist reports and runbooks."
        )
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("SOTERIA_RENDER_BACKEND_URL", DEFAULT_RENDER_BACKEND_URL),
        help="Render backend base URL. Defaults to SOTERIA_RENDER_BACKEND_URL or production.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.getenv("RENDER_PIPELINE_TIMEOUT_SECONDS", "480")),
        help="How long to wait for persisted pipeline outputs.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=float(os.getenv("RENDER_PIPELINE_POLL_INTERVAL_SECONDS", "10")),
        help="How often to query Supabase for persisted outputs.",
    )
    parser.add_argument(
        "--dispatch-mode",
        choices=("deployed-poller", "direct-report-post"),
        default=os.getenv("RENDER_PIPELINE_DISPATCH_MODE", "deployed-poller"),
        help=(
            "deployed-poller waits for the Render worker. direct-report-post "
            "posts the seeded batch to /api/poller/report to isolate backend pipeline health."
        ),
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    try:
        preflight_render_backend(base_url)
        seeded_satellites = seed_validation_satellites()
        seeded_event = seed_validation_event_window()
        print(
            {
                "render_backend": base_url,
                "expected_reaction_url": f"{base_url}/api/poller/report",
                "dispatch_mode": args.dispatch_mode,
                "seeded_event": seeded_event,
                "seeded_satellite_external_ids": [
                    row.get("external_id") for row in seeded_satellites
                ],
            },
            flush=True,
        )
        if args.dispatch_mode == "direct-report-post":
            post_poller_report(base_url, seeded_event)
        report_rows, runbook_rows = wait_for_pipeline_outputs(
            event_window_id=str(seeded_event["id"]),
            seeded_satellite_external_ids={
                str(row["external_id"]) for row in seeded_satellites
            },
            timeout_seconds=args.timeout,
            poll_interval_seconds=args.poll_interval,
        )
    except Exception as exc:
        print(f"Render pipeline validation failed: {exc}", file=sys.stderr)
        return 1

    print(
        {
            "persisted_report_count": len(report_rows),
            "persisted_runbook_count": len(runbook_rows),
            "report_ids": [row.get("id") for row in report_rows[:5]],
            "runbook_satellite_external_ids": sorted(
                {
                    str(row.get("satellite_external_id"))
                    for row in runbook_rows
                    if row.get("satellite_external_id")
                }
            ),
        },
        flush=True,
    )
    print("Render poller pipeline validation passed.")
    return 0


def preflight_render_backend(base_url: str) -> None:
    health_status = request_status(base_url, "GET", "/healthz")
    if health_status != 200:
        raise RuntimeError(f"Render health check returned HTTP {health_status}")
    route_status = request_status(base_url, "POST", "/api/poller/report", body=b"{}")
    if route_status == 404:
        raise RuntimeError("Render backend is missing /api/poller/report")
    if route_status != 422:
        raise RuntimeError(
            "Render /api/poller/report route preflight expected HTTP 422 for "
            f"an empty body, got HTTP {route_status}"
        )


def request_status(
    base_url: str,
    method: str,
    path: str,
    *,
    body: bytes | None = None,
) -> int:
    headers = {"accept": "application/json"}
    if body is not None:
        headers["content-type"] = "application/json"
    request = Request(
        f"{base_url}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=30) as response:
            response.read()
            return response.status
    except HTTPError as exc:
        exc.read()
        return exc.code
    except URLError as exc:
        raise RuntimeError(f"{method} {path} failed: {exc}") from exc


def seed_validation_satellites() -> list[dict[str, Any]]:
    now_sql = "now()"
    rows_sql = ", ".join(
        [
            validation_satellite_values(
                "soteria-render-cubesat-alpha",
                "Soteria Render CubeSat Alpha",
                "LEO",
                410.0,
                "validation_payload",
                now_sql,
            ),
            validation_satellite_values(
                "soteria-render-cubesat-beta",
                "Soteria Render CubeSat Beta",
                "LEO",
                525.0,
                "validation_adcs",
                now_sql,
            ),
            validation_satellite_values(
                "soteria-render-cubesat-gamma",
                "Soteria Render CubeSat Gamma",
                "GEO",
                35786.0,
                "validation_comm",
                now_sql,
            ),
        ]
    )
    sql = f"""
insert into public.satellites (
  external_id, norad_cat_id, name, operator, country, mission_class,
  operational_status, orbit_regime, tle_epoch, reference_epoch, mass_kg,
  cross_section_area_m2, drag_coefficient, ballistic_coefficient_kg_m2,
  position_time, latitude_deg, longitude_deg, altitude_km, speed_km_s, updated_at
) values {rows_sql}
on conflict (external_id) do update set
  name = excluded.name,
  operator = excluded.operator,
  country = excluded.country,
  mission_class = excluded.mission_class,
  operational_status = excluded.operational_status,
  orbit_regime = excluded.orbit_regime,
  tle_epoch = excluded.tle_epoch,
  reference_epoch = excluded.reference_epoch,
  mass_kg = excluded.mass_kg,
  cross_section_area_m2 = excluded.cross_section_area_m2,
  drag_coefficient = excluded.drag_coefficient,
  ballistic_coefficient_kg_m2 = excluded.ballistic_coefficient_kg_m2,
  position_time = excluded.position_time,
  latitude_deg = excluded.latitude_deg,
  longitude_deg = excluded.longitude_deg,
  altitude_km = excluded.altitude_km,
  speed_km_s = excluded.speed_km_s,
  updated_at = excluded.updated_at
returning external_id, name, orbit_regime, operational_status;
"""
    return supabase_rows(sql)


def validation_satellite_values(
    external_id: str,
    name: str,
    orbit_regime: str,
    altitude_km: float,
    mission_class: str,
    now_sql: str,
) -> str:
    speed = 7.6 if orbit_regime == "LEO" else 3.07
    return (
        f"('{external_id}', null, '{name}', 'Soteria Render validation', 'US', "
        f"'{mission_class}', 'active', '{orbit_regime}', {now_sql}, {now_sql}, "
        f"12.0, 0.08, 2.2, 68.18, {now_sql}, 0.0, 0.0, {altitude_km}, "
        f"{speed}, {now_sql})"
    )


def seed_validation_event_window() -> dict[str, Any]:
    event_key = hashlib.sha256(
        f"soteria-render-validation:{dt.datetime.now(dt.UTC).isoformat()}".encode(
            "utf-8"
        )
    ).hexdigest()
    sql = f"""
insert into public.space_weather_event_windows (
  event_key, event_type, source_product, source_endpoint, window_start,
  peak_time, window_end, peak_value, peak_severity, threshold_value, units,
  confidence, status, evidence, updated_at
) values (
  '{event_key}',
  'geomagnetic_storm_risk',
  'soteria_render_validation',
  'src/backend/scripts/render_poller_pipeline_validation.py',
  now() - interval '5 minutes',
  now(),
  now() + interval '2 hours',
  7.0,
  3,
  5.0,
  'Kp',
  'forecast',
  'active',
  jsonb_build_object(
    'validation', true,
    'source', 'render_poller_pipeline_validation.py',
    'note', 'Synthetic Render pipeline validation event window.'
  ),
  now()
)
returning id, event_key, event_type, source_product, status, confidence,
          peak_severity, window_start, updated_at, window_end;
"""
    rows = supabase_rows(sql)
    if not rows:
        raise RuntimeError("Supabase did not return the seeded event window")
    return rows[0]


def post_poller_report(base_url: str, seeded_event: dict[str, Any]) -> None:
    now = dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")
    event_window_id = str(seeded_event["id"])
    payload = {
        "trigger_type": "event_windows_changed",
        "trigger_source": "space_weather_event_windows",
        "priority": "high",
        "event_window_ids": [event_window_id],
        "event_windows": [
            {
                "event_window_id": event_window_id,
                "event_key": seeded_event["event_key"],
                "event_type": seeded_event["event_type"],
                "source_product": seeded_event["source_product"],
                "status": seeded_event["status"],
                "confidence": seeded_event["confidence"],
                "priority": "high",
                "peak_severity": seeded_event["peak_severity"],
                "window_start": iso_z(seeded_event["window_start"]),
                "window_end": iso_z(seeded_event["window_end"]),
                "updated_at": iso_z(seeded_event["updated_at"]),
                "detected_at": now,
            }
        ],
        "detected_at": now,
    }
    request = Request(
        f"{base_url}/api/poller/report",
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json", "accept": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=420) as response:
            body = response.read().decode("utf-8", errors="replace")
            print(
                {
                    "direct_report_post_status": response.status,
                    "direct_report_post_body_preview": body[:1000],
                },
                flush=True,
            )
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Render /api/poller/report returned HTTP {exc.code}: {body[:1000]}"
        ) from exc
    except URLError as exc:
        raise RuntimeError(f"Render /api/poller/report failed: {exc}") from exc


def iso_z(value: Any) -> str:
    text = str(value)
    parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC).isoformat().replace("+00:00", "Z")


def wait_for_pipeline_outputs(
    *,
    event_window_id: str,
    seeded_satellite_external_ids: set[str],
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    deadline = time.monotonic() + timeout_seconds
    last_report_rows: list[dict[str, Any]] = []
    last_runbook_rows: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        last_report_rows = query_report_rows(event_window_id)
        last_runbook_rows = query_runbook_rows(event_window_id)
        runbook_external_ids = {
            str(row.get("satellite_external_id"))
            for row in last_runbook_rows
            if row.get("satellite_external_id")
        }
        missing = sorted(seeded_satellite_external_ids - runbook_external_ids)
        print(
            {
                "waiting_for_event_window_id": event_window_id,
                "report_rows": len(last_report_rows),
                "runbook_rows": len(last_runbook_rows),
                "missing_seeded_runbooks": missing,
            },
            flush=True,
        )
        if last_report_rows and last_runbook_rows and not missing:
            return last_report_rows, last_runbook_rows
        time.sleep(poll_interval_seconds)

    raise RuntimeError(
        "Timed out waiting for Render poller pipeline outputs. "
        f"last_report_rows={len(last_report_rows)} "
        f"last_runbook_rows={len(last_runbook_rows)}"
    )


def query_report_rows(event_window_id: str) -> list[dict[str, Any]]:
    return supabase_rows(
        f"""
select id, event_window_id, status, session_id, created_at
from public.satellite_event_reports
where event_window_id = '{event_window_id}'
order by created_at desc
limit 20;
"""
    )


def query_runbook_rows(event_window_id: str) -> list[dict[str, Any]]:
    return supabase_rows(
        f"""
select id, report_id, event_window_id, satellite_external_id, status,
       catalog_version, policy_version, risk_level, created_at
from public.command_runbooks
where event_window_id = '{event_window_id}'
order by created_at desc
limit 250;
"""
    )


def supabase_rows(sql: str) -> list[dict[str, Any]]:
    payload = run_supabase_query(sql)
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise RuntimeError(f"Unexpected Supabase CLI response: {payload}")
    return [row for row in rows if isinstance(row, dict)]


def run_supabase_query(sql: str) -> dict[str, Any]:
    result = subprocess.run(
        ["supabase", "db", "query", "--linked", "--output", "json", sql],
        text=True,
        capture_output=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return parse_supabase_json(result.stdout)


def parse_supabase_json(output: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    payloads: list[dict[str, Any]] = []
    index = 0
    while index < len(output):
        start = output.find("{", index)
        if start < 0:
            break
        try:
            payload, end = decoder.raw_decode(output[start:])
        except json.JSONDecodeError:
            index = start + 1
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
        index = start + end

    if not payloads:
        raise RuntimeError(f"Supabase CLI did not return JSON: {output[:500]}")
    for payload in reversed(payloads):
        if isinstance(payload.get("rows"), list):
            return payload
    return payloads[-1]


if __name__ == "__main__":
    raise SystemExit(main())
