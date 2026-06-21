from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from agent.command_catalog import CommandArg, CommandRecord, get_catalog_command


SCRIPT_LANGUAGE = "ruby"
SCRIPT_FORMAT_VERSION = "openc3-ruby-runbook.v1"

_FORBIDDEN_SCRIPT_TOKENS = (
    "cmd_no_checks",
    "cmd_no_hazardous_check",
    "UDPSocket",
    "TCPSocket",
    "Net::HTTP",
    "http://",
    "https://",
    "password",
    "credential",
    "secret",
    "token",
)


def render_openc3_ruby_command(
    command: CommandRecord | str,
) -> dict[str, Any]:
    catalog_command = _resolve_command(command)
    _assert_renderable(catalog_command)

    command_args = [_render_arg(arg) for arg in catalog_command.args]
    ruby = _render_ruby(catalog_command, command_args)
    _assert_policy_compliant_ruby(ruby)

    return {
        "script_language": SCRIPT_LANGUAGE,
        "script_format_version": SCRIPT_FORMAT_VERSION,
        "catalog_version": catalog_command.catalog_version,
        "catalog_command_id": catalog_command.id,
        "target": catalog_command.target,
        "command": catalog_command.command,
        "args": command_args,
        "simulator_only": catalog_command.simulator_only,
        "human_review_required": catalog_command.human_review_required,
        "preconditions": list(catalog_command.preconditions),
        "verifier": catalog_command.verifier.model_dump(mode="json"),
        "timeout_seconds": catalog_command.timeout_seconds,
        "ruby": ruby,
    }


def render_openc3_ruby_runbook(
    commands: Iterable[CommandRecord | str],
) -> dict[str, Any]:
    rendered_commands = [
        render_openc3_ruby_command(command)
        for command in commands
    ]
    ruby = "\n\n".join(
        rendered_command["ruby"]
        for rendered_command in rendered_commands
    )
    _assert_policy_compliant_ruby(ruby)

    catalog_versions = sorted(
        {
            rendered_command["catalog_version"]
            for rendered_command in rendered_commands
        }
    )
    return {
        "script_language": SCRIPT_LANGUAGE,
        "script_format_version": SCRIPT_FORMAT_VERSION,
        "catalog_versions": catalog_versions,
        "commands": rendered_commands,
        "ruby": ruby,
    }


def _resolve_command(command: CommandRecord | str) -> CommandRecord:
    if isinstance(command, CommandRecord):
        return command
    return get_catalog_command(command)


def _assert_renderable(command: CommandRecord) -> None:
    if not command.is_executable:
        raise ValueError(
            f"catalog command {command.id!r} cannot render executable Ruby"
        )
    if command.target is None or command.command is None or command.verifier is None:
        raise ValueError(
            f"catalog command {command.id!r} is missing renderable command fields"
        )


def _render_arg(arg: CommandArg) -> dict[str, Any]:
    value = _arg_value(arg)
    _assert_safe_value(value, f"argument {arg.name}")
    return {
        "name": arg.name,
        "type": arg.type,
        "value": value,
    }


def _arg_value(arg: CommandArg) -> Any:
    if arg.value is not None:
        return arg.value
    if arg.default is not None:
        return arg.default
    if arg.scenario_example is not None:
        return arg.scenario_example
    raise ValueError(f"catalog arg {arg.name!r} has no renderable value")


def _render_ruby(
    command: CommandRecord,
    rendered_args: list[dict[str, Any]],
) -> str:
    verifier = command.verifier
    if verifier is None:
        raise ValueError(f"catalog command {command.id!r} has no verifier")

    precondition_lines = [
        f"# Precondition: {precondition}"
        for precondition in command.preconditions
    ]
    header = [
        "# Soteria simulator-only OpenC3 Ruby runbook snippet.",
        "# Human-reviewable; verify the catalog command before simulator use.",
        f"# Catalog command: {command.id}",
        *precondition_lines,
    ]

    command_line = f'cmd("{_ruby_escape(_command_expression(command, rendered_args))}")'
    verifier_expr = _tlm_expression(verifier.target, verifier.packet, verifier.item)
    verifier_name = _ruby_identifier(f"{command.id}_{verifier.item}")
    condition = verifier.condition

    if condition.startswith("increments"):
        body = [
            f'before_{verifier_name} = tlm("{_ruby_escape(verifier_expr)}")',
            command_line,
            f'after_{verifier_name} = tlm("{_ruby_escape(verifier_expr)}")',
            f"# Catalog verifier: {condition}",
            (
                f"raise \"{command.id} verifier failed: {verifier.item} did not "
                f"increment\" unless after_{verifier_name}.to_f > "
                f"before_{verifier_name}.to_f"
            ),
        ]
    elif condition.startswith("changes"):
        body = [
            f'before_{verifier_name} = tlm("{_ruby_escape(verifier_expr)}")',
            command_line,
            f'after_{verifier_name} = tlm("{_ruby_escape(verifier_expr)}")',
            f"# Catalog verifier: {condition}",
            (
                f"raise \"{command.id} verifier failed: {verifier.item} did not "
                f"change\" unless after_{verifier_name} != before_{verifier_name}"
            ),
        ]
    elif condition.startswith("equals:"):
        expected = condition.split(":", 1)[1]
        _assert_safe_value(expected, f"verifier {command.id}")
        body = [
            command_line,
            f'{verifier_name} = tlm("{_ruby_escape(verifier_expr)}")',
            f"# Catalog verifier: {condition}",
            (
                f"raise \"{command.id} verifier failed: expected {verifier.item} "
                f"== {expected}\" unless {verifier_name}.to_s == "
                f'"{_ruby_escape(expected)}"'
            ),
        ]
    else:
        body = [
            command_line,
            f'{verifier_name} = tlm("{_ruby_escape(verifier_expr)}")',
            f"# Catalog verifier: {condition}",
            "# Operator review required: compare verifier telemetry with catalog condition.",
        ]

    return "\n".join([*header, *body])


def _command_expression(
    command: CommandRecord,
    rendered_args: list[dict[str, Any]],
) -> str:
    if command.target is None or command.command is None:
        raise ValueError(f"catalog command {command.id!r} has no command expression")
    parts = [command.target, command.command]
    if rendered_args:
        arg_expression = ", ".join(
            f"{arg['name']} {_format_openc3_arg(arg['value'])}"
            for arg in rendered_args
        )
        parts.extend(["with", arg_expression])
    return " ".join(parts)


def _format_openc3_arg(value: Any) -> str:
    if isinstance(value, str):
        return f"'{_ruby_escape(value)}'"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int | float):
        return str(value)
    raise ValueError(f"unsupported OpenC3 command argument value: {value!r}")


def _tlm_expression(target: str, packet: str, item: str) -> str:
    return f"{target} {packet} {item}"


def _ruby_escape(value: str) -> str:
    _assert_safe_value(value, "Ruby string")
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _ruby_identifier(value: str) -> str:
    chars = [
        char.lower() if char.isalnum() else "_"
        for char in value
    ]
    identifier = "".join(chars).strip("_")
    return identifier or "verifier_value"


def _assert_safe_value(value: Any, label: str) -> None:
    if not isinstance(value, str):
        return
    if "\n" in value or "\r" in value:
        raise ValueError(f"{label} cannot contain newlines")
    lowered = value.lower()
    if "://" in lowered or lowered.startswith("udp:"):
        raise ValueError(f"{label} cannot contain endpoint URLs")


def _assert_policy_compliant_ruby(ruby: str) -> None:
    lowered = ruby.lower()
    for token in _FORBIDDEN_SCRIPT_TOKENS:
        if token.lower() in lowered:
            raise ValueError(f"rendered Ruby contains forbidden token: {token}")
