from __future__ import annotations

import json
import logging

from fastapi import APIRouter, BackgroundTasks, status
from pydantic import BaseModel, ConfigDict

from .poller import EventWindowReactionBatch, EventWindowReactionMessage

logger = logging.getLogger("soteria.api.agent")

REACTION_AGENT_NAME = "event-report-agent"

router = APIRouter(prefix="/agent", tags=["agent"])
poller_report_router = APIRouter(prefix="/api/poller", tags=["poller"])


class AgentReactionAccepted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    agent_name: str
    event_window_id: str
    priority: str
    session_id: str


try:
    from agent.command_runbook_generation import generate_command_runbooks_for_reports
    from agent.report_generation import (
        EventWindowReportRunResult,
        generate_reports_for_event_windows,
        persist_report_run_result,
    )
    from agent.report_pipeline import query_active_satellite_evidence
    from agent.tools import _get_supabase_client
except ImportError:
    from command_runbook_generation import generate_command_runbooks_for_reports
    from report_generation import (
        EventWindowReportRunResult,
        generate_reports_for_event_windows,
        persist_report_run_result,
    )
    from report_pipeline import query_active_satellite_evidence
    from tools import _get_supabase_client


@router.post(
    "/reactions",
    response_model=AgentReactionAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_agent_reaction(
    reaction: EventWindowReactionMessage,
    background_tasks: BackgroundTasks,
) -> AgentReactionAccepted:
    """Accept an event-window reaction and schedule agent handling."""
    session_id = f"event-window:{reaction.event_window_id}"
    background_tasks.add_task(run_reaction_agent, reaction, session_id)
    logger.info(
        "accepted reaction event_window_id=%s priority=%s agent=%s",
        reaction.event_window_id,
        reaction.priority,
        REACTION_AGENT_NAME,
    )
    return AgentReactionAccepted(
        status="accepted",
        agent_name=REACTION_AGENT_NAME,
        event_window_id=reaction.event_window_id,
        priority=reaction.priority,
        session_id=session_id,
    )


async def run_reaction_agent(
    reaction: EventWindowReactionMessage,
    session_id: str,
) -> None:
    """Run the first-pass report agent for a reaction message."""
    try:
        from agent.service import ask_soteria_agent

        result = await ask_soteria_agent(
            REACTION_AGENT_NAME,
            build_reaction_agent_message(reaction),
            session_id=session_id,
        )
    except Exception:
        logger.exception(
            "reaction agent failed event_window_id=%s agent=%s",
            reaction.event_window_id,
            REACTION_AGENT_NAME,
        )
        return

    logger.info(
        "reaction agent completed event_window_id=%s agent=%s result_length=%s",
        reaction.event_window_id,
        REACTION_AGENT_NAME,
        len(result),
    )


def build_reaction_agent_message(reaction: EventWindowReactionMessage) -> str:
    payload = json.dumps(reaction.model_dump(mode="json"), indent=2, sort_keys=True)
    return (
        "A space-weather event window changed and needs an operational reaction.\n\n"
        "Use the event-window payload below to draft the next report or follow-up.\n\n"
        f"{payload}"
    )


@poller_report_router.post("/report", response_model=EventWindowReportRunResult)
async def create_poller_report(
    reaction_batch: EventWindowReactionBatch,
) -> EventWindowReportRunResult:
    """Generate validated reports from a Poller event-window batch."""
    session_id = f"poller:{reaction_batch.detected_at.isoformat()}"
    logger.info(
        "accepted poller report batch event_window_count=%s priority=%s session_id=%s",
        len(reaction_batch.event_window_ids),
        reaction_batch.priority,
        session_id,
    )
    client = _get_supabase_client()
    result = await generate_reports_for_event_windows(
        reaction_batch.event_window_ids,
        client=client,
        session_id=session_id,
    )
    try:
        result.persisted_rows_count = persist_report_run_result(client, result)
    except Exception as exc:
        logger.exception("failed to persist poller report result: %s", exc)
        result.persistence_errors.append(str(exc))
    try:
        if result.reports:
            satellite_result = query_active_satellite_evidence(client)
            if satellite_result.validation_errors:
                result.runbook_errors.extend(satellite_result.validation_errors)
            runbook_rows = generate_command_runbooks_for_reports(
                result.reports,
                satellite_result.satellites,
            )
            result.runbooks_generated_count = len(runbook_rows)
            result.runbooks_persisted_count = persist_command_runbook_rows(
                client,
                runbook_rows,
            )
    except Exception as exc:
        logger.exception("failed to generate poller report command runbooks: %s", exc)
        result.runbook_errors.append(str(exc))
    return result


def persist_command_runbook_rows(client, rows: list[dict]) -> int:
    """Upsert generated command runbooks by deterministic dedupe key."""
    if not rows:
        return 0
    response = (
        client.table("command_runbooks")
        .upsert(rows, on_conflict="dedupe_key")
        .execute()
    )
    return len(response.data or rows)
