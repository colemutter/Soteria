from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
from dotenv import load_dotenv

try:
    from .definition import SOTERIA_AGENTS
    from .tools import SOTERIA_ALLOWED_TOOLS, soteria_tools_server
except ImportError:
    from definition import SOTERIA_AGENTS
    from tools import SOTERIA_ALLOWED_TOOLS, soteria_tools_server

BACKEND_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_ROOT / ".env")

DEFAULT_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5-20250929")
DEFAULT_MAX_TURNS = int(os.getenv("CLAUDE_MAX_TURNS", "8"))
DEFAULT_SYSTEM_PROMPT = """
You are Soteria, an orbital and space-weather safety agent. You're goal is to evaluate
""".strip()


def _sdk_env(api_key: str | None = None) -> dict[str, str]:
    resolved_key = (
        api_key
        or os.getenv("ANTHROPIC_API_KEY")
        or os.getenv("CLAUDE_API_KEY")
    )
    return {"ANTHROPIC_API_KEY": resolved_key} if resolved_key else {}


def _normalize_session_id(session_id: str | None) -> str | None:
    if not session_id:
        return None
    try:
        return str(uuid.UUID(session_id))
    except ValueError:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"soteria:{session_id}"))


def build_agent_options(
    *,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    model: str = DEFAULT_MODEL,
    cwd: str | Path | None = None,
    session_id: str | None = None,
    max_turns: int | None = DEFAULT_MAX_TURNS,
    allowed_tools: list[str] | None = None,
    mcp_servers: dict[str, Any] | str | Path | None = None,
    agents: dict[str, Any] | None = None,
    output_format: dict[str, Any] | None = None,
    api_key: str | None = None,
) -> ClaudeAgentOptions:
    """Build the shared Claude Agent SDK configuration for Soteria."""
    return ClaudeAgentOptions(
        system_prompt=system_prompt,
        model=model,
        cwd=cwd,
        session_id=_normalize_session_id(session_id),
        max_turns=max_turns,
        allowed_tools=allowed_tools if allowed_tools is not None else SOTERIA_ALLOWED_TOOLS,
        mcp_servers=mcp_servers if mcp_servers is not None else {"soteria": soteria_tools_server},
        agents=agents if agents is not None else SOTERIA_AGENTS,
        output_format=output_format,
        env=_sdk_env(api_key),
    )


def create_agent_client(
    options: ClaudeAgentOptions | None = None,
    **option_overrides: Any,
) -> ClaudeSDKClient:
    """Create a context-managed Claude agent client.

    Usage:
        async with create_agent_client(session_id=session_id) as client:
            await client.query(user_message)
            async for message in client.receive_response():
                ...
    """
    return ClaudeSDKClient(options=options or build_agent_options(**option_overrides))
