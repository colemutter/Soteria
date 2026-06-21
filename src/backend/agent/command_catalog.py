from __future__ import annotations

import json
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


DEFAULT_CATALOG_PATH = (
    Path(__file__).resolve().parent
    / "catalogs"
    / "nos3_openc3_v1_07_04_cmdcat_20260621.json"
)


class CatalogCommandStatus(StrEnum):
    AUTOMATION_ALLOWED = "automation_allowed"
    AUTOMATION_ALLOWED_WITH_REVIEW = "automation_allowed_with_review"
    MANUAL_ONLY = "manual_only"
    UNRESOLVED = "unresolved"
    UNRESOLVED_REJECTED = "unresolved_rejected"


UNRESOLVED_STATUSES = {
    CatalogCommandStatus.UNRESOLVED,
    CatalogCommandStatus.UNRESOLVED_REJECTED,
}


class Nos3CatalogMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    release: str = Field(min_length=1)
    tag: str = Field(min_length=1)
    commit: str = Field(min_length=1)
    source: str = Field(min_length=1)


class CommandArg(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    type: str = Field(min_length=1)
    allowed_values: list[Any] | dict[str, Any] | None = None
    default: Any | None = None
    value: Any | None = None
    min: int | float | None = None
    max: int | float | None = None
    units: str | None = None
    scenario_example: Any | None = None

    @model_validator(mode="after")
    def validate_selected_values(self) -> CommandArg:
        self._validate_allowed_member("default", self.default)
        self._validate_allowed_member("value", self.value)
        return self

    def _validate_allowed_member(self, field_name: str, value: Any) -> None:
        if value is None or self.allowed_values is None:
            return
        if isinstance(self.allowed_values, dict):
            allowed = set(self.allowed_values) | set(self.allowed_values.values())
        else:
            allowed = set(self.allowed_values)
        if value not in allowed:
            raise ValueError(
                f"{self.name}.{field_name} must be one of allowed_values"
            )


class VerifierTelemetry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str = Field(min_length=1)
    packet: str = Field(min_length=1)
    item: str = Field(min_length=1)
    condition: str = Field(min_length=1)


class SafetyFlags(BaseModel):
    model_config = ConfigDict(extra="forbid")

    simulator_only: bool
    manual_allowed: bool
    automated_allowed: bool
    human_review_required: bool


class CommandRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    catalog_version: str = Field(min_length=1)
    simulator_stack: str = Field(min_length=1)
    nos3_version: str = Field(min_length=1)
    nos3_tag: str = Field(min_length=1)
    nos3_commit: str = Field(min_length=1)
    status: CatalogCommandStatus
    simulator_only: bool
    target: str | None
    command: str | None
    args: list[CommandArg] = Field(default_factory=list)
    intent: str = Field(min_length=1)
    outcomes: list[str] = Field(default_factory=list)
    manual_allowed: bool
    automated_allowed: bool
    human_review_required: bool
    preconditions: list[str] = Field(default_factory=list)
    verifier: VerifierTelemetry | None
    timeout_seconds: int | None
    result_classification: str = Field(min_length=1)

    @property
    def safety_flags(self) -> SafetyFlags:
        return SafetyFlags(
            simulator_only=self.simulator_only,
            manual_allowed=self.manual_allowed,
            automated_allowed=self.automated_allowed,
            human_review_required=self.human_review_required,
        )

    @property
    def is_unresolved(self) -> bool:
        return self.status in UNRESOLVED_STATUSES

    @property
    def is_executable(self) -> bool:
        return (
            not self.is_unresolved
            and self.target is not None
            and self.command is not None
            and self.verifier is not None
        )

    @model_validator(mode="after")
    def validate_command_record(self) -> CommandRecord:
        if self.is_unresolved and self.automated_allowed:
            raise ValueError("unresolved commands cannot be automated_allowed")
        if not self.is_unresolved:
            missing = [
                field_name
                for field_name in ("target", "command", "verifier")
                if getattr(self, field_name) is None
            ]
            if missing:
                raise ValueError(
                    f"executable command {self.id} is missing {', '.join(missing)}"
                )
        return self


class CommandCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    catalog_version: str = Field(min_length=1)
    simulator_stack: str = Field(min_length=1)
    nos3: Nos3CatalogMetadata
    submodules: dict[str, str]
    record_defaults: dict[str, str]
    commands: list[CommandRecord] = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def apply_record_defaults(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        defaults = data.get("record_defaults") or {}
        commands = data.get("commands") or []
        return {
            **data,
            "commands": [
                {**defaults, **command}
                for command in commands
                if isinstance(command, dict)
            ],
        }

    @model_validator(mode="after")
    def validate_catalog(self) -> CommandCatalog:
        seen: set[str] = set()
        duplicates: list[str] = []
        for command in self.commands:
            if command.id in seen:
                duplicates.append(command.id)
            seen.add(command.id)
            if command.catalog_version != self.catalog_version:
                raise ValueError(
                    f"command {command.id} catalog_version does not match catalog"
                )
            if command.simulator_stack != self.simulator_stack:
                raise ValueError(
                    f"command {command.id} simulator_stack does not match catalog"
                )
        if duplicates:
            raise ValueError(f"duplicate command IDs: {sorted(set(duplicates))}")
        return self

    def command_by_id(self, command_id: str) -> CommandRecord:
        for command in self.commands:
            if command.id == command_id:
                return command
        raise KeyError(f"unknown catalog command_id: {command_id}")


@lru_cache(maxsize=8)
def _load_command_catalog(catalog_path: str) -> CommandCatalog:
    with Path(catalog_path).open() as catalog_file:
        payload = json.load(catalog_file)
    return CommandCatalog.model_validate(payload)


def load_command_catalog(path: Path | str | None = None) -> CommandCatalog:
    catalog_path = Path(path) if path is not None else DEFAULT_CATALOG_PATH
    return _load_command_catalog(str(catalog_path))


def get_catalog_command(command_id: str) -> CommandRecord:
    return load_command_catalog().command_by_id(command_id)


def find_catalog_commands(
    *,
    intent: str | None = None,
    outcome: str | None = None,
    status: CatalogCommandStatus | str | None = None,
    automated_allowed: bool | None = None,
) -> list[CommandRecord]:
    wanted_status = CatalogCommandStatus(status) if status is not None else None
    matches: list[CommandRecord] = []
    for command in load_command_catalog().commands:
        if intent is not None and command.intent != intent:
            continue
        if outcome is not None and outcome not in command.outcomes:
            continue
        if wanted_status is not None and command.status != wanted_status:
            continue
        if (
            automated_allowed is not None
            and command.automated_allowed is not automated_allowed
        ):
            continue
        if automated_allowed is True and not command.is_executable:
            continue
        matches.append(command)
    return matches


def assert_catalog_command_ids(
    command_ids: list[str] | tuple[str, ...],
) -> list[CommandRecord]:
    catalog = load_command_catalog()
    known_ids = {command.id for command in catalog.commands}
    unknown = [
        command_id
        for command_id in command_ids
        if command_id not in known_ids
    ]
    if unknown:
        raise ValueError(f"unknown catalog command IDs: {unknown}")
    return [catalog.command_by_id(command_id) for command_id in command_ids]
