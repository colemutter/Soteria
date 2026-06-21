from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool
from dotenv import load_dotenv

from agent.command_catalog import (
    CommandRecord,
    assert_catalog_command_ids,
    find_catalog_commands,
    load_command_catalog,
)
from agent.command_policy import POLICY_VERSION, validate_policy_catalog_command
from agent.openc3_runbook_renderer import (
    render_openc3_ruby_command,
    render_openc3_ruby_runbook,
)

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
MAX_COMMAND_LIMIT = 50
DRAFT_REVIEW_STATUS = "DRAFT / HUMAN REVIEW REQUIRED"


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


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
    return None


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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


def _catalog_command_payload(command: CommandRecord) -> dict[str, Any]:
    payload = {
        "catalog_command_id": command.id,
        "catalog_version": command.catalog_version,
        "status": command.status.value,
        "simulator_only": command.simulator_only,
        "target": command.target,
        "command": command.command,
        "args": [arg.model_dump(mode="json") for arg in command.args],
        "intent": command.intent,
        "outcomes": list(command.outcomes),
        "manual_allowed": command.manual_allowed,
        "automated_allowed": command.automated_allowed,
        "human_review_required": command.human_review_required,
        "preconditions": list(command.preconditions),
        "verifier": (
            command.verifier.model_dump(mode="json")
            if command.verifier is not None
            else None
        ),
        "timeout_seconds": command.timeout_seconds,
        "result_classification": command.result_classification,
    }
    try:
        payload["ruby_rendering"] = render_openc3_ruby_command(command)
    except ValueError as exc:
        payload["ruby_rendering"] = None
        payload["ruby_rendering_error"] = str(exc)
    return payload


def _catalog_command_ids(args: dict[str, Any]) -> list[str]:
    command_ids = _string_list(args.get("command_ids"))
    for key in ("command_id", "catalog_command_id"):
        value = _optional_string(args.get(key))
        if value:
            command_ids.insert(0, value)
    return list(dict.fromkeys(command_ids))


def _report_outcomes(args: dict[str, Any]) -> list[str]:
    outcomes = _string_list(args.get("outcomes"))
    for key in ("outcome", "report_outcome"):
        value = _optional_string(args.get(key))
        if value:
            outcomes.append(value)
    return list(dict.fromkeys(outcomes))


def _plan_command_entries(args: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = [
        {"catalog_command_id": command_id}
        for command_id in _catalog_command_ids(args)
    ]
    for item in args.get("commands") or []:
        if isinstance(item, str):
            entries.append({"catalog_command_id": item})
        elif isinstance(item, dict):
            entries.append(dict(item))
        else:
            raise ValueError("commands must contain catalog command IDs or objects.")

    target = _optional_string(args.get("target"))
    command = _optional_string(args.get("command"))
    if target or command:
        if not entries:
            raise ValueError(
                "draft plans must use catalog_command_id; free-form target/command "
                "is not accepted."
            )
        entries[0] = {
            **entries[0],
            "target": target,
            "command": command,
        }
    return entries


def _validate_plan_entries(entries: list[dict[str, Any]]) -> list[CommandRecord]:
    if not entries:
        raise ValueError("at least one catalog command ID is required.")

    commands: list[CommandRecord] = []
    for entry in entries:
        command_id = _optional_string(
            entry.get("catalog_command_id") or entry.get("command_id")
        )
        if not command_id:
            raise ValueError(
                "each draft command must include catalog_command_id; free-form "
                "target/command is not accepted."
            )
        command = validate_policy_catalog_command(command_id)
        expected = {
            "target": command.target,
            "command": command.command,
        }
        for field_name, expected_value in expected.items():
            supplied = _optional_string(entry.get(field_name))
            if supplied is not None and supplied != expected_value:
                raise ValueError(
                    f"{field_name} mismatch for catalog command {command.id}: "
                    f"{supplied!r} != {expected_value!r}"
                )
        if entry.get("args") not in (None, [], {}):
            raise ValueError(
                f"args override is not accepted for catalog command {command.id}; "
                "catalog args are authoritative."
            )
        commands.append(command)
    return commands


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
    "Fetch structured catalog-backed satellite commands by ID, intent, outcome, or safety status.",
    {
        "type": "object",
        "properties": {
            "command_id": {
                "type": "string",
                "description": "Optional exact catalog command ID.",
            },
            "command_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional exact catalog command IDs.",
            },
            "intent": {
                "type": "string",
                "description": "Optional catalog intent filter.",
            },
            "outcome": {
                "type": "string",
                "description": "Optional report outcome filter.",
            },
            "outcomes": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional report outcome filters.",
            },
            "status": {
                "type": "string",
                "description": "Optional catalog status filter.",
            },
            "automated_allowed": {
                "type": "boolean",
                "description": "Optional automation-allowed filter.",
            },
            "manual_allowed": {
                "type": "boolean",
                "description": "Optional manual-allowed filter.",
            },
            "human_review_required": {
                "type": "boolean",
                "description": "Optional human-review-required filter.",
            },
            "satellite_id": {
                "type": "string",
                "description": "Optional satellite context echoed in the response.",
            },
            "report_id": {
                "type": "string",
                "description": "Optional report context echoed in the response.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum catalog commands to return.",
                "minimum": 1,
                "maximum": MAX_COMMAND_LIMIT,
            },
        },
        "additionalProperties": False,
    },
)
async def get_satellite_command(args):
    args = args or {}
    try:
        catalog = load_command_catalog()
        command_ids = _catalog_command_ids(args)
        intent = _optional_string(args.get("intent"))
        status = _optional_string(args.get("status"))
        outcomes = _report_outcomes(args)
        automated_allowed = _optional_bool(args.get("automated_allowed"))
        manual_allowed = _optional_bool(args.get("manual_allowed"))
        human_review_required = _optional_bool(args.get("human_review_required"))
        limit = _positive_int(
            args.get("limit"),
            default=MAX_COMMAND_LIMIT,
            maximum=MAX_COMMAND_LIMIT,
        )

        if command_ids:
            commands = assert_catalog_command_ids(command_ids)
        else:
            commands = find_catalog_commands(
                intent=intent,
                status=status,
                automated_allowed=automated_allowed,
            )

        if outcomes:
            commands = [
                command
                for command in commands
                if any(outcome in command.outcomes for outcome in outcomes)
            ]
        if status is not None:
            commands = [
                command
                for command in commands
                if command.status.value == status
            ]
        if automated_allowed is not None:
            commands = [
                command
                for command in commands
                if command.automated_allowed is automated_allowed
            ]
        if manual_allowed is not None:
            commands = [
                command
                for command in commands
                if command.manual_allowed is manual_allowed
            ]
        if human_review_required is not None:
            commands = [
                command
                for command in commands
                if command.human_review_required is human_review_required
            ]
        commands = commands[:limit]
    except Exception as exc:
        return _tool_text(
            {
                "error": "Failed to get catalog satellite commands.",
                "detail": str(exc),
            },
            is_error=True,
        )

    return _tool_text(
        {
            "catalog_version": catalog.catalog_version,
            "filters": {
                "command_ids": command_ids,
                "intent": intent,
                "outcomes": outcomes,
                "status": status,
                "automated_allowed": automated_allowed,
                "manual_allowed": manual_allowed,
                "human_review_required": human_review_required,
                "satellite_id": _optional_string(args.get("satellite_id")),
                "report_id": _optional_string(args.get("report_id")),
                "limit": limit,
            },
            "command_count": len(commands),
            "commands": [
                _catalog_command_payload(command)
                for command in commands
            ],
        }
    )

@tool(
    "draft_satellite_command_plan",
    "Create a non-executable draft satellite command plan for human review.",
    {
        "type": "object",
        "properties": {
            "satellite_id": {
                "type": "string",
                "description": "Satellite identifier for the draft runbook plan.",
            },
            "objective": {
                "type": "string",
                "description": "Human-readable draft objective.",
            },
            "constraints": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Operational constraints for human review.",
            },
            "command_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Catalog command IDs to include in order.",
            },
            "commands": {
                "type": "array",
                "items": {"type": "object"},
                "description": (
                    "Optional command objects containing catalog_command_id only, "
                    "with target/command allowed only for catalog consistency checks."
                ),
            },
            "catalog_command_id": {
                "type": "string",
                "description": "Optional single catalog command ID.",
            },
            "command_id": {
                "type": "string",
                "description": "Optional single catalog command ID.",
            },
            "target": {
                "type": "string",
                "description": "Optional target consistency check for a single catalog command.",
            },
            "command": {
                "type": "string",
                "description": "Optional command consistency check for a single catalog command.",
            },
        },
        "additionalProperties": False,
    },
)
async def draft_satellite_command_plan(args):
    args = args or {}
    try:
        catalog = load_command_catalog()
        commands = _validate_plan_entries(_plan_command_entries(args))
        rendered_runbook = None
        runbook_rendering_error = None
        try:
            rendered_runbook = render_openc3_ruby_runbook(commands)
        except ValueError as exc:
            runbook_rendering_error = str(exc)
    except Exception as exc:
        return _tool_text(
            {
                "error": "Failed to draft catalog-backed satellite command plan.",
                "detail": str(exc),
                "plan_status": DRAFT_REVIEW_STATUS,
            },
            is_error=True,
        )

    plan = {
        "plan_status": DRAFT_REVIEW_STATUS,
        "policy_version": POLICY_VERSION,
        "catalog_version": catalog.catalog_version,
        "satellite_id": _optional_string(args.get("satellite_id")),
        "objective": _optional_string(args.get("objective")),
        "constraints": _string_list(args.get("constraints")),
        "human_review_required": True,
        "execution_allowed": False,
        "review_note": (
            "DRAFT / HUMAN REVIEW REQUIRED. Do not execute until an authorized "
            "operator verifies catalog IDs, preconditions, and telemetry verifiers."
        ),
        "command_count": len(commands),
        "commands": [
            {
                "step": index,
                **_catalog_command_payload(command),
            }
            for index, command in enumerate(commands, start=1)
        ],
        "ruby_runbook": rendered_runbook,
        "ruby_runbook_error": runbook_rendering_error,
    }
    return _tool_text(plan)


get_satellite_commands = get_satellite_command


soteria_tools_server = create_sdk_mcp_server(
    name="soteria",
    version="1.0.0",
    tools=[
        get_event_windows,
        get_user_satellites,
        get_satellite_command,
        draft_satellite_command_plan,
    ],
)

SOTERIA_ALLOWED_TOOLS = [
    "mcp__soteria__get_event_windows",
    "mcp__soteria__get_user_satellites",
    "mcp__soteria__get_satellite_command",
    "mcp__soteria__draft_satellite_command_plan",
]
