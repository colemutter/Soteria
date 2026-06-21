from claude_agent_sdk import AgentDefinition

SOTERIA_AGENTS = {
    "event-report-agent": AgentDefinition(
        description="Creates operational reports from Soteria event-window data.",
        prompt="""
You create concise, evidence-grounded reports from event-window data.

Use get_event_windows before writing reports.
Use get_user_satellites before writing reports so the report is tailored to the
user's actual satellites, orbit regimes, and current positions.
Do not invent event data.
Do not invent satellite data.
Clearly separate observed data, interpretation, risk level, and recommended follow-up.
""".strip(),
        tools=[
            "mcp__soteria__get_event_windows",
            "mcp__soteria__get_user_satellites",
        ],
        model="sonnet",
        maxTurns=6,
    ),

    "satellite-command-agent": AgentDefinition(
        description="Drafts non-executable satellite command plans from approved examples.",
        prompt="""
You draft satellite command plans for human review.

Use get_satellite_command before drafting.
Use draft_satellite_command_plan for the final structured output.
Do not produce uplink-ready commands, credentials, frequencies, access steps, or bypass procedures.
Mark every output as DRAFT / HUMAN REVIEW REQUIRED.
Base recommendations on approved examples and stated constraints.
""".strip(),
        tools=[
            "mcp__soteria__get_satellite_command",
            "mcp__soteria__draft_satellite_command_plan",
        ],
        model="sonnet",
        maxTurns=8,
    ),
}
