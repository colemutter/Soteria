from __future__ import annotations

import json
import os
from typing import Any, Literal

from claude_agent_sdk import ResultMessage
from pydantic import BaseModel, ConfigDict, ValidationError

try:
    from .client import create_agent_client
    from .report_pipeline import build_report_evidence_bundles
    from .report_models import (
        EventWindowSatelliteReport,
        ReportEvidenceBundle,
        report_validation_context,
        report_severity_values,
        satellite_outcome_values,
    )
except ImportError:
    from client import create_agent_client
    from report_pipeline import build_report_evidence_bundles
    from report_models import (
        EventWindowSatelliteReport,
        ReportEvidenceBundle,
        report_validation_context,
        report_severity_values,
        satellite_outcome_values,
    )


REPORT_SYSTEM_PROMPT = """
You are Soteria's event-window report drafter.

Draft reports only from the supplied evidence bundle. Do not fetch data with
tools. Do not invent event-window IDs, satellite IDs, severity values, possible
outcomes, measurements, or source products. Choose only from the allowed enum
values in the evidence bundle and return structured JSON matching the schema.
""".strip()


class ReportGenerationFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_window_id: str
    code: Literal[
        "agent_error",
        "missing_structured_output",
        "validation_error",
    ]
    detail: str


class ReportGenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_window_id: str
    report: EventWindowSatelliteReport | None = None
    failure: ReportGenerationFailure | None = None

    @property
    def ok(self) -> bool:
        return self.report is not None and self.failure is None


class EventWindowReportRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["completed", "failed"]
    requested_event_window_ids: list[str]
    resolved_event_window_ids: list[str]
    missing_event_window_ids: list[str]
    reports: list[EventWindowSatelliteReport] = []
    failures: list[ReportGenerationFailure] = []
    validation_errors: list[str] = []
    session_id: str | None = None
    persisted_rows_count: int = 0
    persistence_errors: list[str] = []
    runbooks_generated_count: int = 0
    runbooks_persisted_count: int = 0
    runbook_errors: list[str] = []


def build_report_prompt(bundle: ReportEvidenceBundle) -> str:
    payload = bundle.model_dump(mode="json")
    return "\n\n".join(
        [
            "Create one EventWindowSatelliteReport for this evidence bundle.",
            "Allowed severity values: " + ", ".join(report_severity_values()),
            "Allowed possible outcome values: " + ", ".join(satellite_outcome_values()),
            "Every finding must cite the supplied event_window.id and satellite external_id.",
            "The satellites list is already relevance-filtered by deterministic event/orbit mapping; do not mention satellites absent from the bundle.",
            "Use impact_guidance to write deeper satellite-specific rationale tied to orbit regime, altitude/position data when present, likely outcomes, and operator_focus.",
            "Evidence bundle JSON:",
            json.dumps(payload, indent=2, sort_keys=True),
        ]
    )


async def generate_report_from_bundle(
    bundle: ReportEvidenceBundle,
    *,
    session_id: str | None = None,
    max_attempts: int = 2,
) -> ReportGenerationResult:
    """Generate and validate one report from one deterministic evidence bundle."""
    prompt = build_report_prompt(bundle)
    validation_context = report_validation_context(bundle)
    last_failure: ReportGenerationFailure | None = None

    for attempt in range(1, max(1, max_attempts) + 1):
        attempt_prompt = prompt
        if last_failure is not None:
            attempt_prompt = (
                f"{prompt}\n\nPrevious attempt failed validation: {last_failure.detail}\n"
                "Return corrected structured JSON only."
            )

        result = await _call_structured_report_agent(
            attempt_prompt,
            session_id=session_id,
        )
        if result.is_error:
            return ReportGenerationResult(
                event_window_id=bundle.event_window.id,
                failure=ReportGenerationFailure(
                    event_window_id=bundle.event_window.id,
                    code="agent_error",
                    detail="; ".join(result.errors or [result.result or "agent error"]),
                ),
            )
        if result.structured_output is None:
            last_failure = ReportGenerationFailure(
                event_window_id=bundle.event_window.id,
                code="missing_structured_output",
                detail="Agent returned no structured_output.",
            )
            continue

        try:
            report = EventWindowSatelliteReport.model_validate(
                result.structured_output,
                context=validation_context,
            )
        except ValidationError as exc:
            last_failure = ReportGenerationFailure(
                event_window_id=bundle.event_window.id,
                code="validation_error",
                detail=str(exc),
            )
            continue

        return ReportGenerationResult(
            event_window_id=bundle.event_window.id,
            report=report,
        )

    return ReportGenerationResult(
        event_window_id=bundle.event_window.id,
        failure=last_failure
        or ReportGenerationFailure(
            event_window_id=bundle.event_window.id,
            code="missing_structured_output",
            detail="Agent did not return a validated report.",
        ),
    )


async def _call_structured_report_agent(
    prompt: str,
    *,
    session_id: str | None,
) -> ResultMessage:
    result_message: ResultMessage | None = None
    async with create_agent_client(
        session_id=session_id,
        max_turns=4,
        system_prompt=REPORT_SYSTEM_PROMPT,
        allowed_tools=[],
        mcp_servers={},
        agents={},
        output_format={
            "type": "json_schema",
            "schema": EventWindowSatelliteReport.model_json_schema(),
        },
        api_key=os.getenv("CLAUDE_API_KEY"),
    ) as client:
        await client.query(prompt)
        async for response in client.receive_response():
            if isinstance(response, ResultMessage):
                result_message = response

    if result_message is None:
        return ResultMessage(
            subtype="error",
            duration_ms=0,
            duration_api_ms=0,
            is_error=True,
            num_turns=0,
            session_id=session_id or "",
            errors=["Agent returned no ResultMessage."],
        )
    return result_message


async def generate_reports_for_event_windows(
    event_window_ids: list[str],
    *,
    client: Any,
    session_id: str | None = None,
) -> EventWindowReportRunResult:
    build_result = build_report_evidence_bundles(event_window_ids, client)
    if build_result.failed_closed:
        return EventWindowReportRunResult(
            status="failed",
            requested_event_window_ids=build_result.requested_event_window_ids,
            resolved_event_window_ids=build_result.resolved_event_window_ids,
            missing_event_window_ids=build_result.missing_event_window_ids,
            failures=[
                ReportGenerationFailure(
                    event_window_id=event_window_id,
                    code="validation_error",
                    detail="Event window could not be resolved.",
                )
                for event_window_id in build_result.requested_event_window_ids
            ],
            validation_errors=build_result.validation_errors,
            session_id=session_id,
        )

    reports: list[EventWindowSatelliteReport] = []
    failures: list[ReportGenerationFailure] = []
    for bundle in build_result.bundles:
        result = await generate_report_from_bundle(
            bundle,
            session_id=session_id or f"event-window:{bundle.event_window.id}",
        )
        if result.report is not None:
            reports.append(result.report)
        if result.failure is not None:
            failures.append(result.failure)

    return EventWindowReportRunResult(
        status="failed" if failures else "completed",
        requested_event_window_ids=build_result.requested_event_window_ids,
        resolved_event_window_ids=build_result.resolved_event_window_ids,
        missing_event_window_ids=build_result.missing_event_window_ids,
        reports=reports,
        failures=failures,
        validation_errors=build_result.validation_errors,
        session_id=session_id,
    )


def persist_report_run_result(
    client: Any,
    result: EventWindowReportRunResult,
) -> int:
    rows: list[dict[str, Any]] = []
    for report in result.reports:
        rows.append(
            {
                "dedupe_key": f"report:{report.event_window_id}:{report.evidence_hash}",
                "event_window_id": report.event_window_id,
                "evidence_hash": report.evidence_hash,
                "status": "validated",
                "session_id": result.session_id,
                "report_json": report.model_dump(mode="json"),
                "failure_json": None,
                "validation_errors": result.validation_errors,
            }
        )
    for failure in result.failures:
        rows.append(
            {
                "dedupe_key": (
                    f"failure:{failure.event_window_id}:"
                    f"{failure.code}:{result.session_id or 'no-session'}"
                ),
                "event_window_id": failure.event_window_id,
                "evidence_hash": None,
                "status": "failed",
                "session_id": result.session_id,
                "report_json": None,
                "failure_json": failure.model_dump(mode="json"),
                "validation_errors": result.validation_errors,
            }
        )
    if not rows:
        return 0

    response = (
        client.table("satellite_event_reports")
        .upsert(rows, on_conflict="dedupe_key")
        .execute()
    )
    return len(response.data or rows)
