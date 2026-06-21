from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agent.command_catalog import (
    CatalogCommandStatus,
    CommandCatalog,
    CommandRecord,
    load_command_catalog,
)
from agent.report_models import (
    EventWindowSatelliteReport,
    ReportSeverity,
    SatelliteImpactFinding,
    SatelliteOutcome,
)


POLICY_VERSION = "solar-weather-command-policy.20260621"


class CommandPolicyRiskLevel(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CommandPolicyContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    telemetry_recovery: bool = False
    communications_quiet_posture: bool = False
    payload_recovery_setup: bool = False
    payload_protection: bool = False
    explicit_low_power_switch7_off: bool = False
    explicit_eps_load_shed: bool = False
    prefer_radio_resume: bool = True


class CommandPolicySelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    catalog_command_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    human_review_required: bool
    risk_level: CommandPolicyRiskLevel
    status: CatalogCommandStatus


class CommandPolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_version: str = POLICY_VERSION
    catalog_version: str = Field(min_length=1)
    satellite_id: str = Field(min_length=1)
    selected_commands: list[CommandPolicySelection] = Field(default_factory=list)
    human_review_required: bool
    risk_level: CommandPolicyRiskLevel
    no_action_reason: str | None = None


class CommandPolicyReportResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_version: str = POLICY_VERSION
    catalog_version: str = Field(min_length=1)
    event_window_id: str = Field(min_length=1)
    decisions: list[CommandPolicyDecision] = Field(default_factory=list)


def recommend_command_policy_for_finding(
    finding: SatelliteImpactFinding,
    *,
    report: EventWindowSatelliteReport | None = None,
    satellite_metadata: Mapping[str, Any] | BaseModel | None = None,
    context: CommandPolicyContext | Mapping[str, Any] | None = None,
    catalog_version: str | None = None,
    catalog: CommandCatalog | None = None,
) -> CommandPolicyDecision:
    command_catalog = _resolve_catalog(catalog, catalog_version)
    policy_context = _coerce_context(context)
    metadata = _metadata_dict(satellite_metadata)
    outcomes = _finding_outcomes(finding, report)

    selections: list[CommandPolicySelection] = []
    no_action_reasons: list[str] = []

    if (
        _has_outcome(outcomes, SatelliteOutcome.NO_MATERIAL_SATELLITE_EFFECT_EXPECTED)
        and not _has_explicit_command_context(policy_context)
    ):
        return _no_action_decision(
            finding=finding,
            catalog=command_catalog,
            reason="No material satellite effect expected; no catalog command recommended.",
            risk_level=CommandPolicyRiskLevel.NONE,
            human_review_required=False,
        )

    if (
        _has_outcome(outcomes, SatelliteOutcome.PAYLOAD_NOISE)
        or policy_context.payload_protection
    ):
        if _supports_catalog_command(
            metadata,
            command_id="sample_disable",
            capability="sample_payload",
            default=False,
        ):
            selections.append(
                _selection(
                    "sample_disable",
                    command_catalog,
                    reason=(
                        "Payload/data-quality risk on a satellite profile that "
                        "supports the NOS3 sample payload."
                    ),
                    risk_level=CommandPolicyRiskLevel.LOW,
                )
            )
        else:
            no_action_reasons.append(
                "Payload protection requested, but the satellite profile does not "
                "declare sample payload support."
            )

    if policy_context.payload_recovery_setup:
        if _supports_catalog_command(
            metadata,
            command_id="sample_enable",
            capability="sample_payload",
            default=False,
        ):
            selections.append(
                _selection(
                    "sample_enable",
                    command_catalog,
                    reason="Explicit payload recovery/setup context enables the sample payload.",
                    risk_level=CommandPolicyRiskLevel.LOW,
                )
            )
        else:
            no_action_reasons.append(
                "Payload recovery/setup requested, but the satellite profile does not "
                "declare sample payload support."
            )

    if policy_context.communications_quiet_posture:
        selections.append(
            _selection(
                "radio_disable_output",
                command_catalog,
                reason=(
                    "Explicit communications quiet/low-power posture; telemetry loss "
                    "is expected and requires human review."
                ),
                risk_level=CommandPolicyRiskLevel.MEDIUM,
            )
        )
    elif (
        _has_outcome(outcomes, SatelliteOutcome.COMMUNICATION_DEGRADED)
        and policy_context.telemetry_recovery
    ):
        command_id = (
            "radio_resume_output"
            if policy_context.prefer_radio_resume
            else "radio_enable_output"
        )
        selections.append(
            _selection(
                command_id,
                command_catalog,
                reason="Explicit telemetry recovery context for degraded communications.",
                risk_level=CommandPolicyRiskLevel.LOW,
            )
        )
    elif _has_outcome(outcomes, SatelliteOutcome.COMMUNICATION_DEGRADED):
        no_action_reasons.append(
            "Communication degradation is present, but telemetry recovery or quiet "
            "posture was not explicitly requested."
        )

    if _has_any_outcome(
        outcomes,
        {
            SatelliteOutcome.ADCS_DISTURBANCE,
            SatelliteOutcome.STAR_TRACKER_DEGRADED,
        },
    ):
        selections.append(
            _selection(
                "adcs_set_sunsafe",
                command_catalog,
                reason="ADCS/star-tracker/pointing degradation maps to catalogued sun-safe mode.",
                risk_level=CommandPolicyRiskLevel.HIGH,
            )
        )

    if _has_any_outcome(
        outcomes,
        {
            SatelliteOutcome.INCREASED_DRAG,
            SatelliteOutcome.ORBIT_PREDICTION_DEGRADED,
            SatelliteOutcome.TRACKING_UNCERTAINTY,
            SatelliteOutcome.GNSS_NAVIGATION_DEGRADED,
        },
    ):
        no_action_reasons.append(
            "Orbit, tracking, or navigation degradation has no catalogued NOS3 "
            "maneuver/planning command."
        )

    if _has_any_outcome(
        outcomes,
        {
            SatelliteOutcome.SURFACE_CHARGING,
            SatelliteOutcome.DEEP_DIELECTRIC_CHARGING,
            SatelliteOutcome.SINGLE_EVENT_EFFECTS,
            SatelliteOutcome.SOLAR_ARRAY_DEGRADATION,
        },
    ):
        no_action_reasons.append(
            "Generic radiation or charging protection has no concrete executable "
            "catalog command."
        )

    if policy_context.explicit_low_power_switch7_off:
        selections.append(
            _selection(
                "eps_switch7_off_manual",
                command_catalog,
                reason=(
                    "Explicit NOS3 low-power switch-7 scenario; catalog marks this "
                    "EPS action manual-only."
                ),
                risk_level=CommandPolicyRiskLevel.HIGH,
            )
        )
    elif policy_context.explicit_eps_load_shed:
        no_action_reasons.append(
            "Generic EPS load shedding remains unresolved because no safe load-to-switch "
            "policy exists."
        )

    selections = _deduplicate_selections(selections)
    if selections:
        return CommandPolicyDecision(
            catalog_version=command_catalog.catalog_version,
            satellite_id=finding.satellite_id,
            selected_commands=selections,
            human_review_required=any(
                selection.human_review_required for selection in selections
            ),
            risk_level=_max_risk(selection.risk_level for selection in selections),
            no_action_reason=None,
        )

    return _no_action_decision(
        finding=finding,
        catalog=command_catalog,
        reason=(
            " ".join(no_action_reasons)
            if no_action_reasons
            else "No conservative catalog command mapping matched this finding."
        ),
        risk_level=_no_action_risk(finding, no_action_reasons),
        human_review_required=bool(no_action_reasons),
    )


def recommend_command_policy_for_report(
    report: EventWindowSatelliteReport,
    *,
    satellite_metadata: (
        Mapping[str, Any]
        | BaseModel
        | Mapping[str, Mapping[str, Any] | BaseModel]
        | None
    ) = None,
    context: (
        CommandPolicyContext
        | Mapping[str, Any]
        | Mapping[str, CommandPolicyContext | Mapping[str, Any]]
        | None
    ) = None,
    catalog_version: str | None = None,
    catalog: CommandCatalog | None = None,
) -> CommandPolicyReportResult:
    command_catalog = _resolve_catalog(catalog, catalog_version)
    decisions = [
        recommend_command_policy_for_finding(
            finding,
            report=report,
            satellite_metadata=_metadata_for_satellite(
                satellite_metadata,
                finding.satellite_id,
            ),
            context=_context_for_satellite(context, finding.satellite_id),
            catalog=command_catalog,
        )
        for finding in report.findings
    ]
    return CommandPolicyReportResult(
        catalog_version=command_catalog.catalog_version,
        event_window_id=report.event_window_id,
        decisions=decisions,
    )


def validate_policy_catalog_command(
    command_id: str,
    *,
    catalog: CommandCatalog | None = None,
    catalog_version: str | None = None,
) -> CommandRecord:
    command_catalog = _resolve_catalog(catalog, catalog_version)
    try:
        command = command_catalog.command_by_id(command_id)
    except KeyError as exc:
        raise ValueError(f"policy selected unknown catalog command ID: {command_id}") from exc
    if command.is_unresolved:
        raise ValueError(f"policy cannot select unresolved catalog command: {command_id}")
    return command


def _selection(
    command_id: str,
    catalog: CommandCatalog,
    *,
    reason: str,
    risk_level: CommandPolicyRiskLevel,
) -> CommandPolicySelection:
    command = validate_policy_catalog_command(command_id, catalog=catalog)
    return CommandPolicySelection(
        catalog_command_id=command.id,
        reason=reason,
        human_review_required=command.human_review_required,
        risk_level=risk_level,
        status=command.status,
    )


def _no_action_decision(
    *,
    finding: SatelliteImpactFinding,
    catalog: CommandCatalog,
    reason: str,
    risk_level: CommandPolicyRiskLevel,
    human_review_required: bool,
) -> CommandPolicyDecision:
    return CommandPolicyDecision(
        catalog_version=catalog.catalog_version,
        satellite_id=finding.satellite_id,
        selected_commands=[],
        human_review_required=human_review_required,
        risk_level=risk_level,
        no_action_reason=reason,
    )


def _resolve_catalog(
    catalog: CommandCatalog | None,
    catalog_version: str | None,
) -> CommandCatalog:
    command_catalog = catalog if catalog is not None else load_command_catalog()
    if catalog_version is not None and command_catalog.catalog_version != catalog_version:
        raise ValueError(
            "catalog_version does not match loaded command catalog: "
            f"{catalog_version} != {command_catalog.catalog_version}"
        )
    return command_catalog


def _coerce_context(
    context: CommandPolicyContext | Mapping[str, Any] | None,
) -> CommandPolicyContext:
    if context is None:
        return CommandPolicyContext()
    if isinstance(context, CommandPolicyContext):
        return context
    return CommandPolicyContext.model_validate(dict(context))


def _metadata_dict(
    satellite_metadata: Mapping[str, Any] | BaseModel | None,
) -> dict[str, Any]:
    if satellite_metadata is None:
        return {}
    if isinstance(satellite_metadata, BaseModel):
        return satellite_metadata.model_dump(mode="json")
    return dict(satellite_metadata)


def _metadata_for_satellite(
    satellite_metadata: (
        Mapping[str, Any]
        | BaseModel
        | Mapping[str, Mapping[str, Any] | BaseModel]
        | None
    ),
    satellite_id: str,
) -> Mapping[str, Any] | BaseModel | None:
    if satellite_metadata is None or isinstance(satellite_metadata, BaseModel):
        return satellite_metadata
    if satellite_id in satellite_metadata:
        candidate = satellite_metadata[satellite_id]
        if isinstance(candidate, (Mapping, BaseModel)):
            return candidate
    return satellite_metadata


def _context_for_satellite(
    context: (
        CommandPolicyContext
        | Mapping[str, Any]
        | Mapping[str, CommandPolicyContext | Mapping[str, Any]]
        | None
    ),
    satellite_id: str,
) -> CommandPolicyContext | Mapping[str, Any] | None:
    if context is None or isinstance(context, CommandPolicyContext):
        return context
    if satellite_id in context:
        candidate = context[satellite_id]
        if isinstance(candidate, (CommandPolicyContext, Mapping)):
            return candidate
    return context


def _finding_outcomes(
    finding: SatelliteImpactFinding,
    report: EventWindowSatelliteReport | None,
) -> set[SatelliteOutcome]:
    outcomes = set(finding.possible_outcomes)
    if report is not None:
        outcomes.update(report.possible_outcomes)
    return outcomes


def _has_outcome(
    outcomes: set[SatelliteOutcome],
    outcome: SatelliteOutcome,
) -> bool:
    return outcome in outcomes


def _has_any_outcome(
    outcomes: set[SatelliteOutcome],
    wanted: set[SatelliteOutcome],
) -> bool:
    return bool(outcomes & wanted)


def _has_explicit_command_context(context: CommandPolicyContext) -> bool:
    return any(
        (
            context.telemetry_recovery,
            context.communications_quiet_posture,
            context.payload_recovery_setup,
            context.payload_protection,
            context.explicit_low_power_switch7_off,
            context.explicit_eps_load_shed,
        )
    )


def _supports_catalog_command(
    metadata: Mapping[str, Any],
    *,
    command_id: str,
    capability: str,
    default: bool,
) -> bool:
    supported_ids = _metadata_values(
        metadata,
        ("supported_catalog_command_ids", "catalog_command_ids", "command_ids"),
    )
    if supported_ids:
        return command_id in supported_ids

    unsupported_ids = _metadata_values(
        metadata,
        ("unsupported_catalog_command_ids",),
    )
    if command_id in unsupported_ids:
        return False

    explicit = _explicit_capability(metadata, capability)
    if explicit is not None:
        return explicit

    capabilities = _metadata_values(
        metadata,
        (
            "capabilities",
            "supported_capabilities",
            "payloads",
            "instruments",
            "subsystems",
            "supported_targets",
            "catalog_profile",
        ),
    )
    if capability in capabilities:
        return True
    return default


def _explicit_capability(
    metadata: Mapping[str, Any],
    capability: str,
) -> bool | None:
    keys_by_capability = {
        "sample_payload": (
            "supports_sample_payload",
            "sample_payload_supported",
            "has_sample_payload",
        ),
    }
    for key in keys_by_capability.get(capability, ()):
        if key in metadata:
            return bool(metadata[key])
    return None


def _metadata_values(
    metadata: Mapping[str, Any],
    keys: Sequence[str],
) -> set[str]:
    values: set[str] = set()
    for key in keys:
        if key not in metadata:
            continue
        value = metadata[key]
        if isinstance(value, str):
            values.add(value)
        elif isinstance(value, Mapping):
            values.update(str(item) for item in value)
            values.update(str(item) for item in value.values())
        elif isinstance(value, Sequence):
            values.update(str(item) for item in value)
        else:
            values.add(str(value))
    return {value.strip().lower() for value in values if value.strip()} | {
        value.strip() for value in values if value.strip()
    }


def _deduplicate_selections(
    selections: Sequence[CommandPolicySelection],
) -> list[CommandPolicySelection]:
    deduped: list[CommandPolicySelection] = []
    seen: set[str] = set()
    for selection in selections:
        if selection.catalog_command_id in seen:
            continue
        seen.add(selection.catalog_command_id)
        deduped.append(selection)
    return deduped


def _no_action_risk(
    finding: SatelliteImpactFinding,
    reasons: Sequence[str],
) -> CommandPolicyRiskLevel:
    if not reasons:
        return CommandPolicyRiskLevel.NONE
    if finding.severity in {ReportSeverity.SEVERE, ReportSeverity.EXTREME}:
        return CommandPolicyRiskLevel.HIGH
    if finding.severity in {ReportSeverity.MAJOR, ReportSeverity.MODERATE}:
        return CommandPolicyRiskLevel.MEDIUM
    return CommandPolicyRiskLevel.LOW


def _max_risk(
    risk_levels: Sequence[CommandPolicyRiskLevel],
) -> CommandPolicyRiskLevel:
    order = {
        CommandPolicyRiskLevel.NONE: 0,
        CommandPolicyRiskLevel.LOW: 1,
        CommandPolicyRiskLevel.MEDIUM: 2,
        CommandPolicyRiskLevel.HIGH: 3,
    }
    return max(risk_levels, key=lambda risk_level: order[risk_level])
