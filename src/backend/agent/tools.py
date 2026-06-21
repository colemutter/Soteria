from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool
from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_ROOT / ".env")

EVENT_WINDOW_COLUMNS = (
    "id,event_key,event_type,source_product,source_endpoint,window_start,"
    "peak_time,window_end,peak_value,peak_severity,threshold_value,units,"
    "confidence,status,evidence,updated_at"
)
SATELLITE_REPORT_COLUMNS = (
    "external_id,norad_cat_id,name,operator,country,mission_class,"
    "operational_status,orbit_regime,tle_epoch,reference_epoch,mass_kg,"
    "cross_section_area_m2,drag_coefficient,ballistic_coefficient_kg_m2,"
    "position_time,latitude_deg,longitude_deg,altitude_km,speed_km_s,updated_at"
)
SATELLITE_TLE_COLUMNS = f"{SATELLITE_REPORT_COLUMNS},tle_line1,tle_line2"
DEFAULT_EVENT_HORIZON_HOURS = 24
MAX_EVENT_HORIZON_HOURS = 24 * 14
MAX_EVENT_WINDOW_LIMIT = 200
MAX_SATELLITE_LIMIT = 200


def _tool_text(payload: dict[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    response = {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, sort_keys=True),
            }
        ]
    }
    if is_error:
        response["is_error"] = True
    return response


def _parse_datetime(value: Any) -> dt.datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("end_time must be a non-empty ISO-8601 datetime string.")
    parsed = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


def _iso_z(value: dt.datetime) -> str:
    return value.astimezone(dt.UTC).isoformat().replace("+00:00", "Z")


def _positive_int(value: Any, *, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, maximum))


def _event_types(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _int_list(value: Any) -> list[int]:
    items: list[int] = []
    for item in _string_list(value):
        try:
            items.append(int(item))
        except ValueError:
            continue
    return items


def _get_supabase_client() -> Any:
    url = os.getenv("SUPABASE_URL")
    key = (
        os.getenv("SUPABASE_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
    )
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be configured.")

    from supabase import create_client

    return create_client(url, key)


def _query_event_windows(
    *,
    now: dt.datetime,
    end_time: dt.datetime,
    limit: int,
    event_types: list[str],
) -> list[dict[str, Any]]:
    query = (
        _get_supabase_client()
        .table("space_weather_event_windows")
        .select(EVENT_WINDOW_COLUMNS)
        .lte("window_start", _iso_z(end_time))
        .gte("window_end", _iso_z(now))
        .order("window_start")
        .limit(limit)
    )
    if event_types:
        query = query.in_("event_type", event_types)
    response = query.execute()
    return [dict(row) for row in response.data or []]


def _query_satellites(
    *,
    external_ids: list[str],
    norad_cat_ids: list[int],
    orbit_regimes: list[str],
    operational_status: str | None,
    include_tle: bool,
    limit: int,
) -> list[dict[str, Any]]:
    query = (
        _get_supabase_client()
        .table("satellites")
        .select(SATELLITE_TLE_COLUMNS if include_tle else SATELLITE_REPORT_COLUMNS)
        .order("name")
        .limit(limit)
    )
    if external_ids:
        query = query.in_("external_id", external_ids)
    if norad_cat_ids:
        query = query.in_("norad_cat_id", norad_cat_ids)
    if orbit_regimes:
        query = query.in_("orbit_regime", [item.upper() for item in orbit_regimes])
    if operational_status:
        query = query.eq("operational_status", operational_status)
    response = query.execute()
    return [dict(row) for row in response.data or []]


@tool(
    "get_event_windows",
    "Fetch space-weather event windows that overlap the present through a requested future time.",
    {
        "type": "object",
        "properties": {
            "end_time": {
                "type": "string",
                "description": "Optional ISO-8601 UTC datetime for the end of the query window.",
            },
            "horizon_hours": {
                "type": "integer",
                "description": "Optional number of hours from now to query when end_time is not provided.",
                "minimum": 1,
                "maximum": MAX_EVENT_HORIZON_HOURS,
            },
            "event_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional event_type filters, such as geomagnetic_storm_risk.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum rows to return.",
                "minimum": 1,
                "maximum": MAX_EVENT_WINDOW_LIMIT,
            },
        },
        "additionalProperties": False,
    },
)
async def get_event_windows(args):
    args = args or {}
    now = dt.datetime.now(dt.UTC)
    try:
        if args.get("end_time"):
            end_time = _parse_datetime(args["end_time"])
        else:
            horizon_hours = _positive_int(
                args.get("horizon_hours"),
                default=DEFAULT_EVENT_HORIZON_HOURS,
                maximum=MAX_EVENT_HORIZON_HOURS,
            )
            end_time = now + dt.timedelta(hours=horizon_hours)

        if end_time <= now:
            return _tool_text(
                {
                    "error": "end_time must be in the future.",
                    "now": _iso_z(now),
                    "end_time": _iso_z(end_time),
                },
                is_error=True,
            )

        limit = _positive_int(
            args.get("limit"),
            default=50,
            maximum=MAX_EVENT_WINDOW_LIMIT,
        )
        filters = _event_types(args.get("event_types"))
        rows = await asyncio.to_thread(
            _query_event_windows,
            now=now,
            end_time=end_time,
            limit=limit,
            event_types=filters,
        )
    except Exception as exc:
        return _tool_text(
            {
                "error": "Failed to get event windows.",
                "detail": str(exc),
            },
            is_error=True,
        )

    return _tool_text(
        {
            "query_window": {
                "start_time": _iso_z(now),
                "end_time": _iso_z(end_time),
                "event_types": filters,
                "limit": limit,
            },
            "event_window_count": len(rows),
            "event_windows": rows,
        }
    )


@tool(
    "get_user_satellites",
    "Fetch user satellite records from the database for space-weather event reports.",
    {
        "type": "object",
        "properties": {
            "external_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional satellite external_id filters.",
            },
            "norad_cat_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Optional NORAD catalog id filters.",
            },
            "orbit_regimes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional orbit regime filters such as LEO, MEO, GEO, or HEO.",
            },
            "operational_status": {
                "type": "string",
                "description": "Optional status filter, usually active.",
            },
            "include_tle": {
                "type": "boolean",
                "description": "Whether to include TLE line fields in the response.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum rows to return.",
                "minimum": 1,
                "maximum": MAX_SATELLITE_LIMIT,
            },
        },
        "additionalProperties": False,
    },
)
async def get_user_satellites(args):
    args = args or {}
    try:
        external_ids = _string_list(args.get("external_ids"))
        norad_cat_ids = _int_list(args.get("norad_cat_ids"))
        orbit_regimes = _string_list(args.get("orbit_regimes"))
        operational_status = args.get("operational_status")
        if operational_status is not None:
            operational_status = str(operational_status).strip() or None
        include_tle = bool(args.get("include_tle", False))
        limit = _positive_int(
            args.get("limit"),
            default=50,
            maximum=MAX_SATELLITE_LIMIT,
        )

        rows = await asyncio.to_thread(
            _query_satellites,
            external_ids=external_ids,
            norad_cat_ids=norad_cat_ids,
            orbit_regimes=orbit_regimes,
            operational_status=operational_status,
            include_tle=include_tle,
            limit=limit,
        )
    except Exception as exc:
        return _tool_text(
            {
                "error": "Failed to get user satellites.",
                "detail": str(exc),
            },
            is_error=True,
        )

    return _tool_text(
        {
            "filters": {
                "external_ids": external_ids,
                "norad_cat_ids": norad_cat_ids,
                "orbit_regimes": orbit_regimes,
                "operational_status": operational_status,
                "include_tle": include_tle,
                "limit": limit,
            },
            "satellite_count": len(rows),
            "satellites": rows,
        }
    )


@tool(
    "get_satellite_command",
    "Fetch approved satellite commands for the given satellite type and operation.",
    {"satellite_type": str, "operation": str},
)
async def get_satellite_commands(args):

    return {
        "content": [
            {
                "type": "text",
                "text": "Return redacted command here.",
            }
        ]
    }

@tool(
    "draft_satellite_command_plan",
    "Create a non-executable draft satellite command plan for human review.",
    {"satellite_id": str, "objective": str, "constraints": str},
)
async def draft_satellite_command_plan(args):
    # This should produce a reviewed draft, not uplink-ready commands.
    return {
        "content": [
            {
                "type": "text",
                "text": "Return draft command plan here.",
            }
        ]
    }


soteria_tools_server = create_sdk_mcp_server(
    name="soteria",
    version="1.0.0",
    tools=[
        get_event_windows,
        get_user_satellites,
        get_satellite_commands,
        draft_satellite_command_plan,
    ],
)

SOTERIA_ALLOWED_TOOLS = [
    "mcp__soteria__get_event_windows",
    "mcp__soteria__get_user_satellites",
    "mcp__soteria__get_satellite_command",
    "mcp__soteria__draft_satellite_command_plan",
]
