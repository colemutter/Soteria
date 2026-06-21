import asyncio
import os

from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock


try:
    from .client import DEFAULT_SYSTEM_PROMPT, create_agent_client
    from .definition import SOTERIA_AGENTS
except ImportError:
    from client import DEFAULT_SYSTEM_PROMPT, create_agent_client
    from definition import SOTERIA_AGENTS


async def ask_soteria(message: str, session_id: str | None = None):
    text_parts: list[str] = []
    final_result: str | None = None

    async with create_agent_client(
        session_id=session_id,
        max_turns=10,
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        api_key=os.getenv("CLAUDE_API_KEY"),
    ) as client:
        await client.query(message)
        async for response in client.receive_response():
            if isinstance(response, AssistantMessage):
                text_parts.extend(
                    block.text
                    for block in response.content
                    if isinstance(block, TextBlock)
                )
            elif isinstance(response, ResultMessage):
                final_result = response.result

    return final_result or "".join(text_parts).strip()


async def ask_soteria_agent(
    agent_name: str,
    message: str,
    session_id: str | None = None,
) -> str:
    if agent_name not in SOTERIA_AGENTS:
        known_agents = ", ".join(sorted(SOTERIA_AGENTS))
        raise ValueError(f"Unknown Soteria agent '{agent_name}'. Use one of: {known_agents}")

    return await ask_soteria(
        f"Use the {agent_name} agent to handle this request:\n\n{message}",
        session_id=session_id,
    )


if __name__ == "__main__":
    print(
        asyncio.run(
            ask_soteria_agent(
                "event-report-agent",
                "Create a short report for the latest event windows.",
            )
        )
    )
