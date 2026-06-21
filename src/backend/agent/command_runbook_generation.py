from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel

from agent.command_catalog import CommandCatalog, CommandRecord, load_command_catalog
from agent.command_policy import (
    POLICY_VERSION,
    CommandPolicyContext,
    CommandPolicyDecision,
    CommandPolicyRiskLevel,
    recommend_command_policy_for_finding,
)
from agent.command_runbook_persistence import validate_catalog_backed_runbook
from agent.openc3_runbook_renderer import render_openc3_ruby_command
from agent.report_models import (
    EventWindowSatelliteReport,
    SatelliteEvidence,
    SatelliteImpactFinding,
)


RUNBOOK_SOURCE = "report_pipeline_catalog"
NO_FINDING_REASON = "Report contains no actionable finding for this satellite."


SatelliteInput = SatelliteEvidence | Mapping[str, Any]
PolicyContextInput = CommandPolicyContext | Mapping[str, Any]


def generate_command_runbooks_for_report(
    report: EventWindowSatelliteReport,
    satellites: Sequence[SatelliteInput],
    *,
    report_id: str | None = None,
    event_window_id: str | None = None,
    evidence_hash: str | None = None,
    satellite_metadata: Mapping[str, Mapping[str, Any] | BaseModel] | None = None,
    policy_context: Mapping[str, PolicyContextInput] | PolicyContextInput | None = None,
    catalog: CommandCatalog | None = None,
) -> list[dict[str, Any]]:
    """Generate one catalog-backed command runbook per report/satellite pair."""
    command_catalog = catalog if catalog is not None else load_command_catalog()
    resolved_event_window_id = event_window_id or report.event_window_id
    resolved_evidence_hash = evidence_hash or report.evidence_hash
    resolved_report_id = (
        report_id
        or f"report:{resolved_event_window_id}:{resolved_evidence_hash}"
    )
    findings_by_satellite = _findings_by_satellite(report.findings)

    rows = [
        _runbook_for_satellite(
            report=report,
            satellite=satellite,
            findings=findings_by_satellite.get(_satellite_external_id(satellite), []),
            report_id=resolved_report_id,
            event_window_id=resolved_event_window_id,
            evidence_hash=resolved_evidence_hash,
            satellite_metadata=satellite_metadata,
            policy_context=policy_context,
            catalog=command_catalog,
        )
        for satellite in satellites
    ]
    return [validate_catalog_backed_runbook(row) for row in rows]


def generate_command_runbooks_for_reports(
    reports: Sequence[EventWindowSatelliteReport],
    satellites: Sequence[SatelliteInput],
    *,
    report_ids: Mapping[str, str] | Sequence[str] | None = None,
    satellite_metadata: Mapping[str, Mapping[str, Any] | BaseModel] | None = None,
    policy_context: Mapping[str, PolicyContextInput] | PolicyContextInput | None = None,
    catalog: CommandCatalog | None = None,
) -> list[dict[str, Any]]:
    """Generate runbooks for every report and every satellite in the query scope."""
    command_catalog = catalog if catalog is not None else load_command_catalog()
    rows: list[dict[str, Any]] = []
    for index, report in enumerate(reports):
        rows.extend(
            generate_command_runbooks_for_report(
                report,
                satellites,
                report_id=_report_id_for_index(report_ids, report, index),
                satellite_metadata=satellite_metadata,
                policy_context=policy_context,
                catalog=command_catalog,
            )
        )
    return rows


def _runbook_for_satellite(
    *,
    report: EventWindowSatelliteReport,
    satellite: SatelliteInput,
    findings: Sequence[SatelliteImpactFinding],
    report_id: str,
    event_window_id: str,
    evidence_hash: str,
    satellite_metadata: Mapping[str, Mapping[str, Any] | BaseModel] | None,
    policy_context: Mapping[str, PolicyContextInput] | PolicyContextInput | None,
    catalog: CommandCatalog,
) -> dict[str, Any]:
    satellite_payload = _satellite_payload(satellite)
    satellite_external_id = _satellite_external_id(satellite)
    satellite_database_id = _satellite_database_id(satellite_payload)
    combined_metadata = _combined_satellite_metadata(
        satellite_payload,
        satellite_metadata,
        satellite_external_id,
    )
    context = _policy_context_for_satellite(policy_context, satellite_external_id)

    if not findings:
        return _no_action_row(
            report=report,
            satellite_payload=satellite_payload,
            satellite_external_id=satellite_external_id,
            satellite_database_id=satellite_database_id,
            report_id=report_id,
            event_window_id=event_window_id,
            evidence_hash=evidence_hash,
            catalog=catalog,
            reason=NO_FINDING_REASON,
            risk_level=CommandPolicyRiskLevel.NONE,
            human_review_required=False,
            policy_decisions=[],
        )

    decisions = [
        recommend_command_policy_for_finding(
            finding,
            report=report,
            satellite_metadata=combined_metadata,
            context=context,
            catalog=catalog,
        )
        for finding in findings
    ]
    selected_commands = _selected_commands(decisions, catalog)
    if not selected_commands:
        return _no_action_row(
            report=report,
            satellite_payload=satellite_payload,
            satellite_external_id=satellite_external_id,
            satellite_database_id=satellite_database_id,
            report_id=report_id,
            event_window_id=event_window_id,
            evidence_hash=evidence_hash,
            catalog=catalog,
            reason=_combined_no_action_reason(decisions),
            risk_level=_max_decision_risk(decisions),
            human_review_required=any(
                decision.human_review_required for decision in decisions
            ),
            policy_decisions=decisions,
            findings=findings,
        )

    commands = [_command_step(command) for command in selected_commands]
    return _base_row(
        report=report,
        satellite_payload=satellite_payload,
        satellite_external_id=satellite_external_id,
        satellite_database_id=satellite_database_id,
        report_id=report_id,
        event_window_id=event_window_id,
        evidence_hash=evidence_hash,
        catalog=catalog,
        status="generated",
        commands=commands,
        title=f"Catalog command runbook for {_satellite_name(satellite_payload)}",
        summary=_generated_summary(report, satellite_payload, commands),
        risk_level=_max_decision_risk(decisions).value,
        metadata={
            **_provenance_metadata(report, satellite_payload, findings),
            "human_review_required": any(
                decision.human_review_required for decision in decisions
            ),
            "policy_decisions": [
                decision.model_dump(mode="json") for decision in decisions
            ],
            "selected_command_reasons": _selected_command_reasons(decisions),
            "renderer": _renderer_metadata(commands),
        },
    )


def _base_row(
    *,
    report: EventWindowSatelliteReport,
    satellite_payload: dict[str, Any],
    satellite_external_id: str,
    satellite_database_id: str | None,
    report_id: str,
    event_window_id: str,
    evidence_hash: str,
    catalog: CommandCatalog,
    status: str,
    commands: list[dict[str, Any]],
    title: str,
    summary: str,
    risk_level: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "report_id": report_id,
        "event_window_id": event_window_id,
        "satellite_external_id": satellite_external_id,
        "catalog_version": catalog.catalog_version,
        "policy_version": POLICY_VERSION,
        "evidence_hash": evidence_hash,
        "dedupe_key": _dedupe_key(
            report_id=report_id,
            satellite_external_id=satellite_external_id,
            catalog_version=catalog.catalog_version,
        ),
        "title": title,
        "summary": summary,
        "commands": commands,
        "risk_level": risk_level,
        "status": status,
        "source": RUNBOOK_SOURCE,
        "metadata": _json_compatible(metadata),
    }
    if satellite_database_id:
        row["satellite_id"] = satellite_database_id
    return row


def _no_action_row(
    *,
    report: EventWindowSatelliteReport,
    satellite_payload: dict[str, Any],
    satellite_external_id: str,
    satellite_database_id: str | None,
    report_id: str,
    event_window_id: str,
    evidence_hash: str,
    catalog: CommandCatalog,
    reason: str,
    risk_level: CommandPolicyRiskLevel,
    human_review_required: bool,
    policy_decisions: Sequence[CommandPolicyDecision],
    findings: Sequence[SatelliteImpactFinding] = (),
) -> dict[str, Any]:
    return _base_row(
        report=report,
        satellite_payload=satellite_payload,
        satellite_external_id=satellite_external_id,
        satellite_database_id=satellite_database_id,
        report_id=report_id,
        event_window_id=event_window_id,
        evidence_hash=evidence_hash,
        catalog=catalog,
        status="no_action",
        commands=[],
        title=f"No catalog command for {_satellite_name(satellite_payload)}",
        summary=reason,
        risk_level=risk_level.value,
        metadata={
            **_provenance_metadata(report, satellite_payload, findings),
            "no_action_reason": reason,
            "human_review_required": human_review_required,
            "policy_decisions": [
                decision.model_dump(mode="json") for decision in policy_decisions
            ],
        },
    )


def _command_step(command: CommandRecord) -> dict[str, Any]:
    rendered = render_openc3_ruby_command(command)
    return {
        "catalog_command_id": command.id,
        "target": command.target,
        "command": command.command,
        "args": rendered["args"],
        "human_review_required": command.human_review_required,
        "automated_allowed": command.automated_allowed,
        "verifier": rendered["verifier"],
        "rendered_script": rendered["ruby"],
        "script_language": rendered["script_language"],
        "script_format_version": rendered["script_format_version"],
    }


def _selected_commands(
    decisions: Sequence[CommandPolicyDecision],
    catalog: CommandCatalog,
) -> list[CommandRecord]:
    commands: list[CommandRecord] = []
    seen: set[str] = set()
    for decision in decisions:
        for selection in decision.selected_commands:
            if selection.catalog_command_id in seen:
                continue
            seen.add(selection.catalog_command_id)
            commands.append(catalog.command_by_id(selection.catalog_command_id))
    return commands


def _findings_by_satellite(
    findings: Sequence[SatelliteImpactFinding],
) -> dict[str, list[SatelliteImpactFinding]]:
    grouped: dict[str, list[SatelliteImpactFinding]] = {}
    for finding in findings:
        grouped.setdefault(finding.satellite_id, []).append(finding)
    return grouped


def _satellite_payload(satellite: SatelliteInput) -> dict[str, Any]:
    if isinstance(satellite, BaseModel):
        return satellite.model_dump(mode="json")
    return _json_compatible(dict(satellite))


def _satellite_external_id(satellite: SatelliteInput) -> str:
    payload = _satellite_payload(satellite)
    external_id = payload.get("external_id") or payload.get("satellite_external_id")
    if not isinstance(external_id, str) or not external_id.strip():
        raise ValueError("satellite must include external_id")
    return external_id


def _satellite_database_id(payload: Mapping[str, Any]) -> str | None:
    database_id = payload.get("id") or payload.get("satellite_id")
    if database_id is None:
        return None
    return str(database_id)


def _satellite_name(payload: Mapping[str, Any]) -> str:
    name = payload.get("name")
    if isinstance(name, str) and name.strip():
        return name
    external_id = payload.get("external_id") or payload.get("satellite_external_id")
    return str(external_id)


def _combined_satellite_metadata(
    satellite_payload: dict[str, Any],
    satellite_metadata: Mapping[str, Mapping[str, Any] | BaseModel] | None,
    satellite_external_id: str,
) -> dict[str, Any]:
    extra = _metadata_for_satellite(satellite_metadata, satellite_external_id)
    return {**satellite_payload, **extra}


def _metadata_for_satellite(
    satellite_metadata: Mapping[str, Mapping[str, Any] | BaseModel] | None,
    satellite_external_id: str,
) -> dict[str, Any]:
    if satellite_metadata is None:
        return {}
    candidate = satellite_metadata.get(satellite_external_id, {})
    if isinstance(candidate, BaseModel):
        return candidate.model_dump(mode="json")
    return _json_compatible(dict(candidate))


def _policy_context_for_satellite(
    policy_context: Mapping[str, PolicyContextInput] | PolicyContextInput | None,
    satellite_external_id: str,
) -> PolicyContextInput | None:
    if policy_context is None or isinstance(policy_context, CommandPolicyContext):
        return policy_context
    if not isinstance(policy_context, Mapping):
        return policy_context
    if set(policy_context) & set(CommandPolicyContext.model_fields):
        return policy_context
    candidate = policy_context.get(satellite_external_id)
    if isinstance(candidate, (CommandPolicyContext, Mapping)):
        return candidate
    return None


def _report_id_for_index(
    report_ids: Mapping[str, str] | Sequence[str] | None,
    report: EventWindowSatelliteReport,
    index: int,
) -> str | None:
    if report_ids is None:
        return None
    if isinstance(report_ids, Mapping):
        return report_ids.get(report.event_window_id)
    return report_ids[index]


def _combined_no_action_reason(
    decisions: Sequence[CommandPolicyDecision],
) -> str:
    reasons = [
        decision.no_action_reason.strip()
        for decision in decisions
        if decision.no_action_reason and decision.no_action_reason.strip()
    ]
    return " ".join(reasons) or "Policy selected no safe catalog command."


def _selected_command_reasons(
    decisions: Sequence[CommandPolicyDecision],
) -> list[dict[str, str]]:
    return [
        {
            "catalog_command_id": selection.catalog_command_id,
            "reason": selection.reason,
        }
        for decision in decisions
        for selection in decision.selected_commands
    ]


def _provenance_metadata(
    report: EventWindowSatelliteReport,
    satellite_payload: dict[str, Any],
    findings: Sequence[SatelliteImpactFinding],
) -> dict[str, Any]:
    return {
        "provenance": {
            "source": RUNBOOK_SOURCE,
            "event_window_id": report.event_window_id,
            "evidence_hash": report.evidence_hash,
            "event_severity": report.event_severity.value,
            "report_summary": report.summary,
            "report_confidence": report.confidence,
            "report_possible_outcomes": [
                outcome.value for outcome in report.possible_outcomes
            ],
            "validation_notes": list(report.validation_notes),
        },
        "satellite": satellite_payload,
        "findings": [
            finding.model_dump(mode="json") for finding in findings
        ],
    }


def _renderer_metadata(commands: Sequence[dict[str, Any]]) -> dict[str, Any]:
    if not commands:
        return {}
    first = commands[0]
    return {
        "script_language": first.get("script_language"),
        "script_format_version": first.get("script_format_version"),
    }


def _generated_summary(
    report: EventWindowSatelliteReport,
    satellite_payload: Mapping[str, Any],
    commands: Sequence[dict[str, Any]],
) -> str:
    command_ids = ", ".join(command["catalog_command_id"] for command in commands)
    return (
        f"{_satellite_name(satellite_payload)} has {len(commands)} catalog-backed "
        f"command step(s) for event window {report.event_window_id}: {command_ids}."
    )


def _dedupe_key(
    *,
    report_id: str,
    satellite_external_id: str,
    catalog_version: str,
) -> str:
    return (
        f"runbook:{report_id}:{satellite_external_id}:"
        f"{catalog_version}:{POLICY_VERSION}"
    )


def _max_decision_risk(
    decisions: Sequence[CommandPolicyDecision],
) -> CommandPolicyRiskLevel:
    if not decisions:
        return CommandPolicyRiskLevel.NONE
    order = {
        CommandPolicyRiskLevel.NONE: 0,
        CommandPolicyRiskLevel.LOW: 1,
        CommandPolicyRiskLevel.MEDIUM: 2,
        CommandPolicyRiskLevel.HIGH: 3,
    }
    return max((decision.risk_level for decision in decisions), key=order.__getitem__)


def _json_compatible(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {
            str(item_key): _json_compatible(item_value)
            for item_key, item_value in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_compatible(item) for item in value]
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value
