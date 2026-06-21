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

Use get_satellite_command before drafting and select only returned catalog_command_id values.
Use draft_satellite_command_plan for the final structured output.
Do not invent OpenC3 targets, command names, arguments, credentials, frequencies, access steps, or bypass procedures.
Do not emit no-check helpers such as cmd_no_checks or cmd_no_hazardous_check.
Mark every output as DRAFT / HUMAN REVIEW REQUIRED and preserve that wording.
Base recommendations on catalog records, verifiers, preconditions, and stated constraints.
If no catalog command fits, say no catalog-backed command is available instead of creating a substitute.
""".strip(),
        tools=[
            "mcp__soteria__get_satellite_command",
            "mcp__soteria__draft_satellite_command_plan",
        ],
        model="sonnet",
        maxTurns=8,
    ),
}
