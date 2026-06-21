# Catalog-Backed Command Runbook Pipeline

Generated: 2026-06-21

This document describes the current operator contract for catalog-backed CubeSat
command runbooks and the future OpenC3 execution bridge boundary. The pipeline
produces human-reviewable NOS3/OpenC3 simulator runbooks only. It does not
automate command execution.

## Source Of Truth

The runtime catalog is loaded from
`src/backend/agent/catalogs/nos3_openc3_v1_07_04_cmdcat_20260621.json` by
`src/backend/agent/command_catalog.py`. Its source document is
`docs/cubesat-openc3-command-catalog.md`.

Current catalog identity:

- `catalog_version`: `nos3-openc3-v1_07_04-cmdcat.20260621`
- `simulator_stack`: `nos3_openc3`
- NOS3 release/tag: `1.7.4` / `v1_07_04`
- NOS3 commit: `4428de566833527c49b16d322157ed11ad8f2318`

Catalog records carry the command ID, OpenC3 target, command name, typed args,
preconditions, verifier telemetry, result classification, source evidence, and
safety flags. The backend validates catalog shape and rejects duplicate IDs,
unresolved automated commands, and executable records missing target, command,
or verifier fields.

## Report To Runbook Flow

1. `/api/poller/report` in `src/backend/api/agent.py` generates and persists
   validated event-window reports.
2. The same endpoint queries active satellite evidence with
   `query_active_satellite_evidence`.
3. `src/backend/agent/command_runbook_generation.py` calls
   `generate_command_runbooks_for_reports`.
4. For every report and every satellite in the query result, the generator
   creates exactly one `command_runbooks` row.
5. `src/backend/agent/command_policy.py` maps report findings to conservative
   catalog command IDs or a no-action decision.
6. `src/backend/agent/openc3_runbook_renderer.py` renders operator Ruby snippets
   from catalog records.
7. `validate_catalog_backed_runbook` in
   `src/backend/agent/command_runbook_persistence.py` validates each row before
   persistence.

The one-runbook-per-satellite guarantee is implemented by iterating the full
satellite query result for every report. A satellite with no finding still gets
a runbook row with `status = "no_action"`. A satellite with findings but no safe
catalog mapping also gets a `no_action` row.

## Stored Runbook Contract

Every generated runbook row stores provenance and enforcement fields:

- `report_id`, `event_window_id`, `satellite_id` or `satellite_external_id`
- `catalog_version`, `policy_version`, `evidence_hash`, `dedupe_key`
- `status`: `generated` or `no_action`
- `source`: `report_pipeline_catalog`
- `risk_level`
- `metadata.provenance`, `metadata.findings`, `metadata.policy_decisions`

Generated runbooks contain `commands[]` steps. Each command step must include:

- `catalog_command_id`
- `target`
- `command`
- `args`
- `human_review_required`
- `automated_allowed`
- `verifier`
- optional operator artifact fields such as `rendered_script`,
  `script_language`, and `script_format_version`

`status = "no_action"` means the runbook is intentionally empty. It must not
include command steps, and it must include `metadata.no_action_reason`. This is
not a failure case; it is how the pipeline records "reviewed, no safe catalog
command selected" while preserving the one-runbook-per-satellite invariant.

## Policy Examples

`sample_disable`

- Intent: disable the NOS3 sample payload for payload/data-quality protection.
- Catalog target/command: `SAMPLE_RADIO` / `SAMPLE_DISABLE_CC`.
- Args: none.
- Verifier storage: `SAMPLE_RADIO SAMPLE_HK_TLM DEVICE_ENABLED` with condition
  `equals:DISABLED`.
- Policy use: selected only when the finding or context indicates payload
  protection and the satellite metadata supports the sample payload.

`radio_enable_output`

- Intent: enable radio telemetry output for communications recovery.
- Catalog target/command: `CFS_RADIO` / `TO_ENABLE_OUTPUT`.
- Args: `DEST_IP = "radio-sim"`, `DEST_PORT = 5011`.
- Verifier storage: `CFS_RADIO TO_HKPACKET ENABLEDROUTES` with condition
  `changes_or_radio_packets_fresh`.
- Policy use: selected for explicit telemetry recovery when the context prefers
  enabling output rather than resuming a paused route.

`adcs_set_sunsafe`

- Intent: set the generic ADCS simulator to sun-safe mode.
- Catalog target/command: `GENERIC_ADCS` / `GENERIC_ADCS_SET_MODE_CC`.
- Args: `GNC_MODE = SUNSAFE_MODE`.
- Verifier storage: `GENERIC_ADCS GENERIC_ADCS_GNC MODE` with condition
  `equals:SUNSAFE`.
- Policy use: selected for ADCS, star-tracker, or pointing degradation and
  marked high risk with human review required.

## Ruby Renderer Notes

The Ruby snippet is derived output, not the authority. The authority is the
stored catalog command ID plus catalog-backed target, command, args, verifier,
and safety flags.

`src/backend/agent/openc3_runbook_renderer.py` renders OpenC3 Ruby with:

- `cmd("TARGET COMMAND ...")` for command send syntax.
- `tlm("TARGET PACKET ITEM")` for verifier reads.
- typed args from catalog defaults, values, or scenario examples.
- script metadata: `script_language = "ruby"` and
  `script_format_version = "openc3-ruby-runbook.v1"`.

The renderer forbids no-check helpers and network/secrets tokens, including
`cmd_no_checks`, `cmd_no_hazardous_check`, `UDPSocket`, `TCPSocket`, `Net::HTTP`,
endpoint URLs, passwords, credentials, secrets, and tokens. No-check helpers are
forbidden because they bypass OpenC3 command and hazardous checks. Soteria's
contract is to preserve catalog validation, human review, precondition checks,
and telemetry verification rather than rendering scripts that can skip safety
gates.

## Future Bridge Contract

A future OpenC3 bridge must consume structured catalog-backed steps, not
`rendered_script` text. The bridge should treat Ruby as an operator display
artifact and perform its own execution from:

- `catalog_command_id`
- `target`
- `command`
- `args`
- `preconditions` from the catalog
- `verifier`
- `human_review_required`
- `automated_allowed`
- `catalog_version` and `policy_version`

Future bridge checklist:

- Use a private OpenC3 API path only.
- Load OpenC3/API authentication from a secrets manager.
- Re-load and validate the catalog command ID before command send.
- Check target visibility, allowed args, scenario preconditions, expiry, and
  human-review state.
- Send the command through OpenC3, not through a public raw command endpoint.
- Run the stored telemetry verifier after send.
- Persist command result, verifier result, timestamps, operator/automation
  identity, and failure classification.
- Do not expose a public raw command endpoint that accepts target, command, or
  Ruby text directly.

## Automation Remaining Work

Before execution can be automated, the repo still needs:

- an OpenC3 bridge implementation behind a private authenticated API;
- secrets-manager integration for OpenC3 credentials;
- a durable approval/review state for `human_review_required` commands;
- precondition evaluation against live OpenC3 target and telemetry state;
- command send result persistence and retry/failure policy;
- telemetry verifier execution and result storage;
- bridge-level allowlist enforcement by `catalog_command_id`;
- operator UI for reviewing `generated` and `no_action` rows;
- explicit prohibition of public raw command/Ruby execution endpoints.

## Local Verification Checklist

Use this checklist after changing the report/runbook pipeline:

- Seed or fake `N` active satellites.
- Generate or fake an event-window report.
- Run the `/api/poller/report` pipeline or the equivalent local report pipeline.
- Query `command_runbooks`.
- Confirm there are `N` runbooks per report.
- Confirm no-action cases have `status = "no_action"`, empty `commands`, and
  `metadata.no_action_reason`.
- Confirm every non-empty command step has `catalog_command_id`.
- Confirm every command step's `target`, `command`, `args`,
  `human_review_required`, `automated_allowed`, and `verifier` match the loaded
  catalog record.
- Confirm Ruby in `rendered_script` derives from catalog records and contains no
  forbidden no-check helpers.

## Relevant Files

- `agents/catalog-backed-command-runbooks-subtasks.md`
- `docs/cubesat-openc3-command-catalog.md`
- `src/backend/agent/catalogs/nos3_openc3_v1_07_04_cmdcat_20260621.json`
- `src/backend/agent/command_catalog.py`
- `src/backend/agent/command_policy.py`
- `src/backend/agent/openc3_runbook_renderer.py`
- `src/backend/agent/command_runbook_generation.py`
- `src/backend/agent/command_runbook_persistence.py`
- `src/backend/api/agent.py`
- `src/backend/api/operations.py`
