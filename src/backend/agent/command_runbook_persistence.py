from __future__ import annotations

from typing import Any

from agent.command_catalog import CommandArg, CommandRecord, load_command_catalog


REQUIRED_CATALOG_RUNBOOK_FIELDS = (
    "event_window_id",
    "catalog_version",
    "policy_version",
    "evidence_hash",
    "dedupe_key",
)

REQUIRED_COMMAND_STEP_FIELDS = (
    "catalog_command_id",
    "target",
    "command",
    "args",
    "human_review_required",
    "automated_allowed",
    "verifier",
)


def validate_catalog_backed_runbook(row: dict[str, Any]) -> dict[str, Any]:
    """Validate a generated command runbook row before persistence."""
    catalog = load_command_catalog()
    _require_non_empty_strings(row, REQUIRED_CATALOG_RUNBOOK_FIELDS)
    if row["catalog_version"] != catalog.catalog_version:
        raise ValueError(
            "catalog_version must match the loaded command catalog "
            f"({catalog.catalog_version})"
        )
    if not row.get("satellite_id") and not row.get("satellite_external_id"):
        raise ValueError("runbook must identify a satellite")

    status = row.get("status") or "generated"
    row["status"] = status
    commands = row.get("commands") or []
    metadata = row.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be an object")

    if status == "no_action":
        if commands:
            raise ValueError("no_action runbooks must not include commands")
        reason = metadata.get("no_action_reason")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("no_action runbooks require metadata.no_action_reason")
        return row

    if status != "generated":
        raise ValueError("generated runbooks must use status 'generated' or 'no_action'")
    if not commands:
        raise ValueError(
            "generated runbooks must include command steps or use no_action "
            "with metadata.no_action_reason"
        )
    if not isinstance(commands, list):
        raise ValueError("commands must be a list")

    for index, step in enumerate(commands):
        _validate_command_step(index, step, catalog.command_by_id)
    return row


def _require_non_empty_strings(row: dict[str, Any], field_names: tuple[str, ...]) -> None:
    missing = [
        field_name
        for field_name in field_names
        if not isinstance(row.get(field_name), str) or not row[field_name].strip()
    ]
    if missing:
        raise ValueError(f"missing required runbook fields: {', '.join(missing)}")


def _validate_command_step(
    index: int,
    step: Any,
    command_by_id: Any,
) -> None:
    if not isinstance(step, dict):
        raise ValueError(f"commands[{index}] must be an object")
    _require_non_empty_strings(step, ("catalog_command_id", "target", "command"))
    missing = [field for field in REQUIRED_COMMAND_STEP_FIELDS if field not in step]
    if missing:
        raise ValueError(
            f"commands[{index}] missing required fields: {', '.join(missing)}"
        )

    try:
        catalog_command = command_by_id(step["catalog_command_id"])
    except KeyError as exc:
        raise ValueError(str(exc)) from exc
    if not catalog_command.is_executable:
        raise ValueError(
            f"commands[{index}].catalog_command_id is not executable: "
            f"{catalog_command.id}"
        )

    _require_equal(index, "target", step["target"], catalog_command.target)
    _require_equal(index, "command", step["command"], catalog_command.command)
    _require_equal(
        index,
        "human_review_required",
        step["human_review_required"],
        catalog_command.human_review_required,
    )
    _require_equal(
        index,
        "automated_allowed",
        step["automated_allowed"],
        catalog_command.automated_allowed,
    )

    expected_verifier = catalog_command.verifier.model_dump(mode="json")
    if step["verifier"] != expected_verifier:
        raise ValueError(
            f"commands[{index}].verifier must match catalog command "
            f"{catalog_command.id}"
        )
    if "rendered_script" in step and not isinstance(step["rendered_script"], str):
        raise ValueError(f"commands[{index}].rendered_script must be a string")

    _validate_args(index, step["args"], catalog_command)


def _require_equal(index: int, field_name: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        raise ValueError(
            f"commands[{index}].{field_name} must match catalog value {expected!r}"
        )


def _validate_args(index: int, selected_args: Any, catalog_command: CommandRecord) -> None:
    if not isinstance(selected_args, list):
        raise ValueError(f"commands[{index}].args must be a list")

    catalog_args = {arg.name: arg for arg in catalog_command.args}
    selected_names: list[str] = []
    for arg_index, selected_arg in enumerate(selected_args):
        if not isinstance(selected_arg, dict):
            raise ValueError(
                f"commands[{index}].args[{arg_index}] must be an object"
            )
        name = selected_arg.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(
                f"commands[{index}].args[{arg_index}].name is required"
            )
        selected_names.append(name)
        catalog_arg = catalog_args.get(name)
        if catalog_arg is None:
            raise ValueError(
                f"commands[{index}].args[{arg_index}].name is not in catalog: {name}"
            )
        _validate_catalog_arg_metadata(index, arg_index, selected_arg, catalog_arg)
        _validate_arg_value(index, arg_index, selected_arg, catalog_arg)

    if set(selected_names) != set(catalog_args):
        raise ValueError(
            f"commands[{index}].args must match catalog arg names "
            f"{sorted(catalog_args)}"
        )
    if len(selected_names) != len(set(selected_names)):
        raise ValueError(f"commands[{index}].args contains duplicate arg names")


def _validate_catalog_arg_metadata(
    index: int,
    arg_index: int,
    selected_arg: dict[str, Any],
    catalog_arg: CommandArg,
) -> None:
    catalog_payload = catalog_arg.model_dump(mode="json")
    for field_name in (
        "type",
        "allowed_values",
        "min",
        "max",
        "units",
        "scenario_example",
    ):
        if (
            field_name in selected_arg
            and selected_arg[field_name] != catalog_payload[field_name]
        ):
            raise ValueError(
                f"commands[{index}].args[{arg_index}].{field_name} must match "
                f"catalog arg {catalog_arg.name}"
            )


def _validate_arg_value(
    index: int,
    arg_index: int,
    selected_arg: dict[str, Any],
    catalog_arg: CommandArg,
) -> None:
    for field_name in ("value", "default"):
        if field_name not in selected_arg:
            continue
        value = selected_arg[field_name]
        _validate_allowed_value(index, arg_index, field_name, value, catalog_arg)
        _validate_numeric_bounds(index, arg_index, field_name, value, catalog_arg)


def _validate_allowed_value(
    index: int,
    arg_index: int,
    field_name: str,
    value: Any,
    catalog_arg: CommandArg,
) -> None:
    if value is None or catalog_arg.allowed_values is None:
        return
    if isinstance(catalog_arg.allowed_values, dict):
        allowed = set(catalog_arg.allowed_values) | set(
            catalog_arg.allowed_values.values()
        )
    else:
        allowed = set(catalog_arg.allowed_values)
    if value not in allowed:
        raise ValueError(
            f"commands[{index}].args[{arg_index}].{field_name} is not allowed "
            f"for catalog arg {catalog_arg.name}"
        )


def _validate_numeric_bounds(
    index: int,
    arg_index: int,
    field_name: str,
    value: Any,
    catalog_arg: CommandArg,
) -> None:
    if value is None or not isinstance(value, int | float):
        return
    if catalog_arg.min is not None and value < catalog_arg.min:
        raise ValueError(
            f"commands[{index}].args[{arg_index}].{field_name} is below "
            f"catalog minimum"
        )
    if catalog_arg.max is not None and value > catalog_arg.max:
        raise ValueError(
            f"commands[{index}].args[{arg_index}].{field_name} is above "
            f"catalog maximum"
        )
