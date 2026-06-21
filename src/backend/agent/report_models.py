from __future__ import annotations

import datetime as dt
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, model_validator


class ReportSeverity(StrEnum):
    NONE = "none"
    MINOR = "minor"
    MODERATE = "moderate"
    MAJOR = "major"
    SEVERE = "severe"
    EXTREME = "extreme"


class SatelliteOutcome(StrEnum):
    INCREASED_DRAG = "increased_drag"
    ORBIT_PREDICTION_DEGRADED = "orbit_prediction_degraded"
    ADCS_DISTURBANCE = "adcs_disturbance"
    SURFACE_CHARGING = "surface_charging"
    DEEP_DIELECTRIC_CHARGING = "deep_dielectric_charging"
    SINGLE_EVENT_EFFECTS = "single_event_effects"
    PAYLOAD_NOISE = "payload_noise"
    STAR_TRACKER_DEGRADED = "star_tracker_degraded"
    SOLAR_ARRAY_DEGRADATION = "solar_array_degradation"
    COMMUNICATION_DEGRADED = "communication_degraded"
    GNSS_NAVIGATION_DEGRADED = "gnss_navigation_degraded"
    TRACKING_UNCERTAINTY = "tracking_uncertainty"
    NO_MATERIAL_SATELLITE_EFFECT_EXPECTED = "no_material_satellite_effect_expected"


def report_severity_values() -> list[str]:
    return [severity.value for severity in ReportSeverity]


def satellite_outcome_values() -> list[str]:
    return [outcome.value for outcome in SatelliteOutcome]


class EvidenceSourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    field: str | None = None


class EventWindowEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    event_key: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    source_product: str = Field(min_length=1)
    status: str = Field(min_length=1)
    confidence: str = Field(min_length=1)
    window_start: dt.datetime
    window_end: dt.datetime
    updated_at: dt.datetime
    source_endpoint: str | None = None
    peak_time: dt.datetime | None = None
    peak_value: float | None = None
    peak_severity: int | None = None
    threshold_value: float | None = None
    units: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)


class SatelliteEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    orbit_regime: str = Field(min_length=1)
    operational_status: str = Field(min_length=1)
    norad_cat_id: int | None = None
    operator: str | None = None
    country: str | None = None
    mission_class: str | None = None
    position_time: dt.datetime | None = None
    latitude_deg: float | None = None
    longitude_deg: float | None = None
    altitude_km: float | None = None
    speed_km_s: float | None = None
    updated_at: dt.datetime | None = None


class SatelliteImpactGuidance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    satellite_id: str = Field(min_length=1)
    orbit_regime: str = Field(min_length=1)
    relevance_reason: str = Field(min_length=1)
    likely_outcomes: list[SatelliteOutcome] = Field(min_length=1)
    rationale_guidance: str = Field(min_length=1)
    operator_focus: list[str] = Field(default_factory=list)


class ReportEvidenceBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_window: EventWindowEvidence
    satellites: list[SatelliteEvidence] = Field(default_factory=list)
    evidence_hash: str = Field(min_length=1)
    allowed_severities: list[ReportSeverity] = Field(
        default_factory=lambda: list(ReportSeverity)
    )
    allowed_outcomes: list[SatelliteOutcome] = Field(
        default_factory=lambda: list(SatelliteOutcome)
    )
    impact_guidance: list[SatelliteImpactGuidance] = Field(default_factory=list)
    satellite_selection_notes: list[str] = Field(default_factory=list)
    source_refs: list[EvidenceSourceRef] = Field(default_factory=list)
    created_at: dt.datetime

    @property
    def event_window_ids(self) -> set[str]:
        return {self.event_window.id}

    @property
    def satellite_ids(self) -> set[str]:
        return {satellite.external_id for satellite in self.satellites}


class SatelliteImpactFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    satellite_id: str = Field(min_length=1)
    severity: ReportSeverity
    possible_outcomes: list[SatelliteOutcome] = Field(min_length=1)
    rationale: str = Field(min_length=1)
    source_event_window_ids: list[str] = Field(min_length=1)
    source_satellite_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_source_references(
        self,
        info: ValidationInfo,
    ) -> SatelliteImpactFinding:
        context = info.context or {}
        event_window_ids = set(context.get("event_window_ids") or [])
        satellite_ids = set(context.get("satellite_ids") or [])

        if event_window_ids:
            unknown_events = sorted(set(self.source_event_window_ids) - event_window_ids)
            if unknown_events:
                raise ValueError(
                    f"finding cites unknown event_window_ids: {unknown_events}"
                )
        if satellite_ids:
            unknown_sources = sorted(set(self.source_satellite_ids) - satellite_ids)
            if unknown_sources:
                raise ValueError(f"finding cites unknown satellite_ids: {unknown_sources}")
            if self.satellite_id not in satellite_ids:
                raise ValueError(f"finding uses unknown satellite_id: {self.satellite_id}")
        return self


class EventWindowSatelliteReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_window_id: str = Field(min_length=1)
    evidence_hash: str = Field(min_length=1)
    event_severity: ReportSeverity
    summary: str = Field(min_length=1)
    possible_outcomes: list[SatelliteOutcome] = Field(min_length=1)
    findings: list[SatelliteImpactFinding] = Field(min_length=1)
    confidence: str = Field(min_length=1)
    validation_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_report_references(
        self,
        info: ValidationInfo,
    ) -> EventWindowSatelliteReport:
        context = info.context or {}
        event_window_ids = set(context.get("event_window_ids") or [])
        evidence_hash = context.get("evidence_hash")

        if event_window_ids and self.event_window_id not in event_window_ids:
            raise ValueError(f"report uses unknown event_window_id: {self.event_window_id}")
        if evidence_hash and self.evidence_hash != evidence_hash:
            raise ValueError("report evidence_hash does not match evidence bundle")

        finding_events = {
            event_id
            for finding in self.findings
            for event_id in finding.source_event_window_ids
        }
        if self.event_window_id not in finding_events:
            raise ValueError("report findings must cite the report event_window_id")
        return self


class EventWindowReportBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reports: list[EventWindowSatelliteReport] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_batch(self, info: ValidationInfo) -> EventWindowReportBatch:
        context = info.context or {}
        expected_ids = set(context.get("event_window_ids") or [])
        report_ids = [report.event_window_id for report in self.reports]
        duplicate_ids = sorted(
            event_id for event_id in set(report_ids) if report_ids.count(event_id) > 1
        )
        if duplicate_ids:
            raise ValueError(f"duplicate event_window_id reports: {duplicate_ids}")
        if expected_ids and set(report_ids) != expected_ids:
            missing = sorted(expected_ids - set(report_ids))
            extra = sorted(set(report_ids) - expected_ids)
            raise ValueError(
                f"report event_window_ids do not match evidence; missing={missing} extra={extra}"
            )
        return self


def report_validation_context(
    bundle: ReportEvidenceBundle,
) -> dict[str, Any]:
    return {
        "event_window_ids": bundle.event_window_ids,
        "satellite_ids": bundle.satellite_ids,
        "evidence_hash": bundle.evidence_hash,
    }
