from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from agent.report_models import (
    EventWindowEvidence,
    EvidenceSourceRef,
    ReportEvidenceBundle,
    SatelliteEvidence,
    SatelliteImpactGuidance,
    SatelliteOutcome,
    report_severity_values,
    satellite_outcome_values,
)
from agent.tools import (
    EVENT_WINDOW_COLUMNS,
    MAX_SATELLITE_LIMIT,
    SATELLITE_REPORT_COLUMNS,
)


DEFAULT_ACTIVE_SATELLITE_STATUS = "active"
DEFAULT_RELEVANT_SATELLITE_LIMIT = 12


class EventWindowResolutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_event_window_ids: list[str] = Field(default_factory=list)
    duplicate_event_window_ids: list[str] = Field(default_factory=list)
    resolved_event_windows: list[EventWindowEvidence] = Field(default_factory=list)
    missing_event_window_ids: list[str] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    failed_closed: bool = False


class SatelliteEvidenceQueryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    satellites: list[SatelliteEvidence] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)


class ReportEvidenceBuildResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bundles: list[ReportEvidenceBundle] = Field(default_factory=list)
    requested_event_window_ids: list[str] = Field(default_factory=list)
    resolved_event_window_ids: list[str] = Field(default_factory=list)
    missing_event_window_ids: list[str] = Field(default_factory=list)
    duplicate_event_window_ids: list[str] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    failed_closed: bool = False


def resolve_event_windows(
    event_window_ids: Sequence[Any],
    client: Any,
) -> EventWindowResolutionResult:
    """Resolve Poller-provided event-window IDs into validated evidence rows.

    Duplicate IDs are queried once and resolved once, preserving the first
    occurrence order. Duplicate values are still reported for observability.
    """

    requested_ids, duplicate_ids, normalization_errors = _normalize_event_window_ids(
        event_window_ids
    )
    if not requested_ids:
        return EventWindowResolutionResult(
            requested_event_window_ids=[],
            duplicate_event_window_ids=duplicate_ids,
            validation_errors=[
                *normalization_errors,
                "event_window_ids must contain at least one non-empty ID.",
            ],
            failed_closed=True,
        )

    rows = _query_event_windows_by_id(client, requested_ids)
    by_id: dict[str, EventWindowEvidence] = {}
    returned_ids: set[str] = set()
    validation_errors = list(normalization_errors)

    for row in rows:
        event_window_id = str(row.get("id") or "").strip()
        if not event_window_id:
            validation_errors.append("event window row is missing id.")
            continue
        if event_window_id not in requested_ids:
            validation_errors.append(
                f"database returned unrequested event_window_id: {event_window_id}"
            )
            continue

        returned_ids.add(event_window_id)
        if event_window_id in by_id:
            validation_errors.append(
                f"database returned duplicate event_window_id: {event_window_id}"
            )
            continue

        try:
            by_id[event_window_id] = EventWindowEvidence.model_validate(dict(row))
        except ValidationError as exc:
            validation_errors.append(
                f"event_window_id={event_window_id} failed validation: {exc}"
            )

    resolved = [
        by_id[event_window_id]
        for event_window_id in requested_ids
        if event_window_id in by_id
    ]
    missing = [
        event_window_id
        for event_window_id in requested_ids
        if event_window_id not in returned_ids
    ]
    failed_closed = not resolved
    if failed_closed:
        validation_errors.append("no requested event_window_ids resolved.")

    return EventWindowResolutionResult(
        requested_event_window_ids=requested_ids,
        duplicate_event_window_ids=duplicate_ids,
        resolved_event_windows=resolved,
        missing_event_window_ids=missing,
        validation_errors=validation_errors,
        failed_closed=failed_closed,
    )


def query_active_satellite_evidence(
    client: Any,
    *,
    limit: int = MAX_SATELLITE_LIMIT,
    operational_status: str = DEFAULT_ACTIVE_SATELLITE_STATUS,
) -> SatelliteEvidenceQueryResult:
    rows = _query_active_satellite_rows(
        client,
        limit=limit,
        operational_status=operational_status,
    )
    satellites: list[SatelliteEvidence] = []
    validation_errors: list[str] = []

    for row in rows:
        row_id = str(row.get("external_id") or "<missing-external-id>")
        evidence_payload = {
            key: row[key]
            for key in SatelliteEvidence.model_fields
            if key in row
        }
        try:
            satellites.append(SatelliteEvidence.model_validate(evidence_payload))
        except ValidationError as exc:
            validation_errors.append(
                f"satellite_external_id={row_id} failed validation: {exc}"
            )

    return SatelliteEvidenceQueryResult(
        satellites=satellites,
        validation_errors=validation_errors,
    )


def build_report_evidence_bundles(
    event_window_ids: Sequence[Any],
    client: Any,
    *,
    created_at: dt.datetime | None = None,
    satellite_limit: int = MAX_SATELLITE_LIMIT,
    max_relevant_satellites: int = DEFAULT_RELEVANT_SATELLITE_LIMIT,
) -> ReportEvidenceBuildResult:
    event_result = resolve_event_windows(event_window_ids, client)
    if event_result.failed_closed:
        return ReportEvidenceBuildResult(
            requested_event_window_ids=event_result.requested_event_window_ids,
            duplicate_event_window_ids=event_result.duplicate_event_window_ids,
            missing_event_window_ids=event_result.missing_event_window_ids,
            validation_errors=event_result.validation_errors,
            failed_closed=True,
        )

    satellite_result = query_active_satellite_evidence(
        client,
        limit=satellite_limit,
    )
    bundle_time = _utc_now() if created_at is None else _as_utc(created_at)
    bundles = [
        _build_report_evidence_bundle(
            event_window=event_window,
            satellites=satellite_result.satellites,
            created_at=bundle_time,
            max_relevant_satellites=max_relevant_satellites,
        )
        for event_window in event_result.resolved_event_windows
    ]

    return ReportEvidenceBuildResult(
        bundles=bundles,
        requested_event_window_ids=event_result.requested_event_window_ids,
        resolved_event_window_ids=[bundle.event_window.id for bundle in bundles],
        missing_event_window_ids=event_result.missing_event_window_ids,
        duplicate_event_window_ids=event_result.duplicate_event_window_ids,
        validation_errors=[
            *event_result.validation_errors,
            *satellite_result.validation_errors,
        ],
        failed_closed=False,
    )


def evidence_hash_for_bundle(
    *,
    event_window: EventWindowEvidence,
    satellites: Sequence[SatelliteEvidence],
    source_refs: Sequence[EvidenceSourceRef],
    impact_guidance: Sequence[SatelliteImpactGuidance],
    satellite_selection_notes: Sequence[str],
) -> str:
    payload = {
        "event_window": event_window.model_dump(mode="json"),
        "satellites": [
            satellite.model_dump(mode="json")
            for satellite in sorted(satellites, key=lambda item: item.external_id)
        ],
        "allowed_severities": report_severity_values(),
        "allowed_outcomes": satellite_outcome_values(),
        "impact_guidance": [
            guidance.model_dump(mode="json")
            for guidance in sorted(
                impact_guidance,
                key=lambda item: item.satellite_id,
            )
        ],
        "satellite_selection_notes": list(satellite_selection_notes),
        "source_refs": [
            source_ref.model_dump(mode="json")
            for source_ref in sorted(
                source_refs,
                key=lambda item: (
                    item.source_type,
                    item.source_id,
                    item.field or "",
                ),
            )
        ],
    }
    canonical_json = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _query_event_windows_by_id(
    client: Any,
    event_window_ids: Sequence[str],
) -> list[dict[str, Any]]:
    response = (
        client.table("space_weather_event_windows")
        .select(EVENT_WINDOW_COLUMNS)
        .in_("id", list(event_window_ids))
        .execute()
    )
    return [dict(row) for row in response.data or []]


def _query_active_satellite_rows(
    client: Any,
    *,
    limit: int,
    operational_status: str,
) -> list[dict[str, Any]]:
    response = (
        client.table("satellites")
        .select(SATELLITE_REPORT_COLUMNS)
        .eq("operational_status", operational_status)
        .order("name")
        .limit(limit)
        .execute()
    )
    return [dict(row) for row in response.data or []]


def _build_report_evidence_bundle(
    *,
    event_window: EventWindowEvidence,
    satellites: Sequence[SatelliteEvidence],
    created_at: dt.datetime,
    max_relevant_satellites: int,
) -> ReportEvidenceBundle:
    selected_satellites, impact_guidance, selection_notes = _select_relevant_satellites(
        event_window=event_window,
        satellites=satellites,
        max_relevant_satellites=max_relevant_satellites,
    )
    source_refs = [
        EvidenceSourceRef(
            source_type="space_weather_event_windows",
            source_id=event_window.id,
        ),
        *[
            EvidenceSourceRef(
                source_type="satellites",
                source_id=satellite.external_id,
            )
            for satellite in selected_satellites
        ],
    ]
    evidence_hash = evidence_hash_for_bundle(
        event_window=event_window,
        satellites=selected_satellites,
        source_refs=source_refs,
        impact_guidance=impact_guidance,
        satellite_selection_notes=selection_notes,
    )
    return ReportEvidenceBundle(
        event_window=event_window,
        satellites=list(selected_satellites),
        impact_guidance=impact_guidance,
        satellite_selection_notes=selection_notes,
        source_refs=source_refs,
        evidence_hash=evidence_hash,
        created_at=created_at,
    )


def _select_relevant_satellites(
    *,
    event_window: EventWindowEvidence,
    satellites: Sequence[SatelliteEvidence],
    max_relevant_satellites: int,
) -> tuple[list[SatelliteEvidence], list[SatelliteImpactGuidance], list[str]]:
    scored: list[tuple[int, str, SatelliteEvidence, SatelliteImpactGuidance]] = []
    for satellite in satellites:
        score, guidance = _satellite_impact_guidance(event_window, satellite)
        if guidance is not None:
            scored.append((score, satellite.name.lower(), satellite, guidance))

    if not scored and satellites:
        notes = [
            "No deterministic event/orbit relevance profile matched; using capped active satellites with no-material-effect guidance."
        ]
        fallback = [
            (
                1,
                satellite.name.lower(),
                satellite,
                SatelliteImpactGuidance(
                    satellite_id=satellite.external_id,
                    orbit_regime=_orbit_regime(satellite),
                    relevance_reason="fallback_active_satellite",
                    likely_outcomes=[
                        SatelliteOutcome.NO_MATERIAL_SATELLITE_EFFECT_EXPECTED
                    ],
                    rationale_guidance=(
                        "The event type does not yet have a deterministic asset-specific "
                        "mapping. Explain uncertainty and avoid asserting unsupported impacts."
                    ),
                    operator_focus=["confirm mission-specific exposure before action"],
                ),
            )
            for satellite in satellites
        ]
        scored = fallback
    else:
        notes = [_selection_note(event_window, len(scored), len(satellites))]

    scored.sort(key=lambda item: (-item[0], item[1], item[2].external_id))
    capped = scored[: max(0, max_relevant_satellites)]
    if len(scored) > len(capped):
        notes.append(
            f"Selected top {len(capped)} of {len(scored)} relevant satellites by deterministic exposure score."
        )

    return (
        [item[2] for item in capped],
        [item[3] for item in capped],
        notes,
    )


def _satellite_impact_guidance(
    event_window: EventWindowEvidence,
    satellite: SatelliteEvidence,
) -> tuple[int, SatelliteImpactGuidance | None]:
    family = _event_family(event_window)
    orbit = _orbit_regime(satellite)
    severity = event_window.peak_severity or 0
    low_altitude_bonus = 20 if _low_leo_altitude(satellite) else 0

    if family == "geomagnetic":
        if orbit == "LEO":
            outcomes = [
                SatelliteOutcome.INCREASED_DRAG,
                SatelliteOutcome.ORBIT_PREDICTION_DEGRADED,
                SatelliteOutcome.ADCS_DISTURBANCE,
                SatelliteOutcome.TRACKING_UNCERTAINTY,
            ]
            if severity >= 3:
                outcomes.append(SatelliteOutcome.SURFACE_CHARGING)
            return 100 + low_altitude_bonus, SatelliteImpactGuidance(
                satellite_id=satellite.external_id,
                orbit_regime=orbit,
                relevance_reason="geomagnetic_leo_drag_and_tracking",
                likely_outcomes=outcomes,
                rationale_guidance=(
                    "For LEO assets, geomagnetic storms heat the upper atmosphere, "
                    "raise neutral density, increase drag and drag torque, and make "
                    "orbit prediction/conjunction screening less reliable. Use altitude, "
                    "speed, ballistic coefficient, and position_time when available."
                ),
                operator_focus=[
                    "fresh orbit determination",
                    "drag and decay review",
                    "conjunction screening margin",
                    "ADCS residual monitoring",
                ],
            )
        if orbit in {"MEO", "GEO", "HEO"} and severity >= 3:
            return 70, SatelliteImpactGuidance(
                satellite_id=satellite.external_id,
                orbit_regime=orbit,
                relevance_reason="geomagnetic_high_orbit_charging",
                likely_outcomes=[
                    SatelliteOutcome.SURFACE_CHARGING,
                    SatelliteOutcome.DEEP_DIELECTRIC_CHARGING,
                    SatelliteOutcome.COMMUNICATION_DEGRADED,
                ],
                rationale_guidance=(
                    "For MEO/GEO/HEO assets, strong geomagnetic activity can enhance "
                    "plasma and energetic electron exposure, raising surface/deep "
                    "charging risk and link-margin sensitivity. Tie rationale to orbit "
                    "regime and avoid LEO drag claims for high-orbit assets."
                ),
                operator_focus=[
                    "charging-sensitive switching deferral",
                    "current/fault telemetry monitoring",
                    "link-margin checks",
                ],
            )
        return 0, None

    if family == "radiation":
        base_score = 100 if orbit in {"MEO", "GEO", "HEO"} else 80
        return base_score, SatelliteImpactGuidance(
            satellite_id=satellite.external_id,
            orbit_regime=orbit,
            relevance_reason="solar_radiation_particle_exposure",
            likely_outcomes=[
                SatelliteOutcome.SINGLE_EVENT_EFFECTS,
                SatelliteOutcome.PAYLOAD_NOISE,
                SatelliteOutcome.SOLAR_ARRAY_DEGRADATION,
                SatelliteOutcome.STAR_TRACKER_DEGRADED,
            ],
            rationale_guidance=(
                "Radiation storm indicators map to single-event effects, detector/payload "
                "noise, star-tracker degradation, and solar-array degradation. Increase "
                "confidence for high-altitude or polar assets when that exposure is present."
            ),
            operator_focus=[
                "EDAC/latchup counters",
                "detector high-voltage posture",
                "critical upload deferral",
            ],
        )

    if family == "charging":
        if orbit in {"MEO", "GEO", "HEO"}:
            return 100, SatelliteImpactGuidance(
                satellite_id=satellite.external_id,
                orbit_regime=orbit,
                relevance_reason="energetic_electron_high_orbit_charging",
                likely_outcomes=[
                    SatelliteOutcome.SURFACE_CHARGING,
                    SatelliteOutcome.DEEP_DIELECTRIC_CHARGING,
                    SatelliteOutcome.SINGLE_EVENT_EFFECTS,
                ],
                rationale_guidance=(
                    "Energetic electron enhancements are most directly relevant to "
                    "surface and deep dielectric charging for high-orbit assets. Discuss "
                    "sensitive switching, eclipse/local-time uncertainty, and current/fault monitoring."
                ),
                operator_focus=[
                    "charging telemetry",
                    "avoid sensitive switching",
                    "fault counter review",
                ],
            )
        return 0, None

    if family == "communications":
        return 60, SatelliteImpactGuidance(
            satellite_id=satellite.external_id,
            orbit_regime=orbit,
            relevance_reason="radio_blackout_or_ionospheric_disturbance",
            likely_outcomes=[
                SatelliteOutcome.COMMUNICATION_DEGRADED,
                SatelliteOutcome.GNSS_NAVIGATION_DEGRADED,
                SatelliteOutcome.TRACKING_UNCERTAINTY,
            ],
            rationale_guidance=(
                "Radio blackout, TEC, and scintillation events mainly affect command/telemetry "
                "links, GNSS navigation, and tracking quality. Keep the rationale focused on "
                "link and navigation uncertainty rather than spacecraft hardware damage."
            ),
            operator_focus=[
                "robust contact windows",
                "link margin",
                "GNSS uncertainty inflation",
            ],
        )

    return 0, None


def _event_family(event_window: EventWindowEvidence) -> str:
    text = " ".join(
        [
            event_window.event_type,
            event_window.source_product,
            str(event_window.evidence),
        ]
    ).lower()
    if any(token in text for token in ("geomagnetic", "kp", "southward_bz", "solar_wind")):
        return "geomagnetic"
    if any(token in text for token in ("proton", "radiation", "solar_particle", "s_scale")):
        return "radiation"
    if any(token in text for token in ("electron", "charging", "dielectric")):
        return "charging"
    if any(token in text for token in ("xray", "radio", "blackout", "r_scale", "tec", "scintillation")):
        return "communications"
    return "generic"


def _selection_note(
    event_window: EventWindowEvidence,
    selected_count: int,
    active_count: int,
) -> str:
    return (
        f"Selected {selected_count} of {active_count} active satellites using "
        f"{_event_family(event_window)} event/orbit relevance mapping."
    )


def _orbit_regime(satellite: SatelliteEvidence) -> str:
    return satellite.orbit_regime.upper().strip() or "UNKNOWN"


def _low_leo_altitude(satellite: SatelliteEvidence) -> bool:
    return (
        _orbit_regime(satellite) == "LEO"
        and satellite.altitude_km is not None
        and satellite.altitude_km < 450
    )


def _normalize_event_window_ids(
    event_window_ids: Sequence[Any],
) -> tuple[list[str], list[str], list[str]]:
    requested_ids: list[str] = []
    duplicate_ids: list[str] = []
    errors: list[str] = []
    seen: set[str] = set()

    for index, raw_id in enumerate(event_window_ids):
        if raw_id is None:
            errors.append(f"event_window_ids[{index}] is empty.")
            continue
        event_window_id = str(raw_id).strip()
        if not event_window_id:
            errors.append(f"event_window_ids[{index}] is empty.")
            continue
        if event_window_id in seen:
            duplicate_ids.append(event_window_id)
            continue
        seen.add(event_window_id)
        requested_ids.append(event_window_id)

    return requested_ids, duplicate_ids, errors


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _as_utc(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.UTC)
    return value.astimezone(dt.UTC)
