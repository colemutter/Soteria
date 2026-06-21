from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from agent.command_runbook_persistence import validate_catalog_backed_runbook

BACKEND_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_ROOT / ".env")

router = APIRouter(prefix="/api", tags=["operations"])

SATELLITE_COLUMNS = (
    "id,external_id,norad_cat_id,name,operator,country,mission_class,"
    "operational_status,orbit_regime,tle_line1,tle_line2,tle_epoch,"
    "reference_epoch,mass_kg,cross_section_area_m2,drag_coefficient,"
    "ballistic_coefficient_kg_m2,position_time,latitude_deg,longitude_deg,"
    "altitude_km,speed_km_s,created_at,updated_at"
)
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


def _execute_query(query: Any, failure_message: str) -> Any:
    try:
        return query.execute()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{failure_message}: {exc}",
        ) from exc


class SatelliteUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_id: str = Field(min_length=1)
    norad_cat_id: int | None = None
    name: str = Field(min_length=1)
    operator: str | None = None
    country: str | None = None
    mission_class: str | None = None
    operational_status: str = "active"
    orbit_regime: str = Field(min_length=1)
    tle_line1: str | None = None
    tle_line2: str | None = None
    tle_epoch: str | None = None
    reference_epoch: str | None = None
    mass_kg: float | None = None
    cross_section_area_m2: float | None = None
    drag_coefficient: float = 2.2
    ballistic_coefficient_kg_m2: float | None = None
    position_time: str | None = None
    latitude_deg: float | None = None
    longitude_deg: float | None = None
    altitude_km: float | None = None
    speed_km_s: float | None = None
    updated_at: str | None = None


class SatelliteUpsertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    satellites: list[SatelliteUpsert] = Field(min_length=1, max_length=200)


class SatelliteListResponse(BaseModel):
    satellites: list[dict[str, Any]]


class SatelliteUpsertResponse(BaseModel):
    status: str
    count: int
    satellites: list[dict[str, Any]]


class CommandRunbookPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    event_window_id: str | None = None
    satellite_id: str | None = None
    satellite_external_id: str | None = None
    catalog_version: str | None = None
    policy_version: str | None = None
    evidence_hash: str | None = None
    dedupe_key: str | None = None
    title: str = Field(min_length=1)
    summary: str | None = None
    commands: list[Any] = Field(default_factory=list)
    risk_level: str = "unknown"
    status: str | None = None
    source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CommandRunbookRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runbook: CommandRunbookPayload


class CommandRunbookResponse(BaseModel):
    status: Literal["accepted", "uploaded"]
    runbook: dict[str, Any]


@router.post(
    "/satellites",
    response_model=SatelliteUpsertResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_satellites(payload: SatelliteUpsertRequest) -> SatelliteUpsertResponse:
    """Upsert frontend-created satellites into Supabase."""
    rows = [satellite.model_dump(exclude_none=True) for satellite in payload.satellites]
    response = _execute_query(
        _get_supabase_client()
        .table("satellites")
        .upsert(rows, on_conflict="external_id"),
        "Failed to upsert satellites",
    )
    data = [dict(row) for row in response.data or []]
    return SatelliteUpsertResponse(status="created", count=len(rows), satellites=data)


@router.get("/satellites", response_model=SatelliteListResponse)
async def get_satellites(
    limit: int = Query(default=100, ge=1, le=200),
    orbit_regime: str | None = None,
    operational_status: str | None = None,
) -> SatelliteListResponse:
    """Fetch satellites from Supabase."""
    query = (
        _get_supabase_client()
        .table("satellites")
        .select(SATELLITE_COLUMNS)
        .order("name")
        .limit(limit)
    )
    if orbit_regime:
        query = query.eq("orbit_regime", orbit_regime.upper())
    if operational_status:
        query = query.eq("operational_status", operational_status)

    response = _execute_query(query, "Failed to fetch satellites")
    return SatelliteListResponse(satellites=[dict(row) for row in response.data or []])


@router.post(
    "/runbooks/generated",
    response_model=CommandRunbookResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def receive_generated_runbook(
    payload: CommandRunbookRequest,
) -> CommandRunbookResponse:
    """Receive an AI-generated command runbook draft."""
    row = payload.runbook.model_dump(exclude_none=True)
    try:
        row = validate_catalog_backed_runbook(row)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    response = _execute_query(
        _get_supabase_client()
        .table("command_runbooks")
        .upsert(row, on_conflict="dedupe_key"),
        "Failed to receive generated runbook",
    )
    data = response.data or [row]
    return CommandRunbookResponse(status="accepted", runbook=dict(data[0]))


@router.post("/runbooks/upload", response_model=CommandRunbookResponse)
async def upload_runbook(payload: CommandRunbookRequest) -> CommandRunbookResponse:
    """Persist a finalized generated command runbook in Supabase."""
    row = payload.runbook.model_dump(exclude_none=True)
    row["status"] = "uploaded"
    response = _execute_query(
        _get_supabase_client().table("command_runbooks").insert(row),
        "Failed to upload runbook",
    )
    data = response.data or [row]
    return CommandRunbookResponse(status="uploaded", runbook=dict(data[0]))
