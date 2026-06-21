from __future__ import annotations

import json
import logging

from fastapi import APIRouter, BackgroundTasks, status
from pydantic import BaseModel, ConfigDict

from .poller import EventWindowReactionMessage

logger = logging.getLogger("soteria.api.agent")

REACTION_AGENT_NAME = "event-report-agent"

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentReactionAccepted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    agent_name: str
    event_window_id: str
    priority: str
    session_id: str


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
