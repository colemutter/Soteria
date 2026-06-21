# CubeSat OpenC3 End-To-End Scenarios

Generated: 2026-06-21

This document designs the first end-to-end slice for a NOS3-backed CubeSat
simulation controlled through OpenC3/COSMOS 5 and recorded through Supabase. It
is simulator-only. It is not a flight command procedure, command authority,
RF uplink path, or claim of flight qualification.

The scope is scenario design and row-level examples only. It does not implement
the agent, bridge, UI, Supabase migrations, OpenC3 targets, or NOS3 extensions.

## Source Basis

| Artifact | Scenario use |
| --- | --- |
| [Command evidence](./cubesat-nos3-command-evidence.md) | Confirms NOS3/OpenC3 is the simulator basis and identifies source-backed seed commands. |
| [T1 bench runbook](./cubesat-nos3-openc3-bench-runbook.md) | Keeps OpenC3 private and validates that the bench exposes fresh cFS/NOS3 telemetry. |
| [T2 command catalog](./cubesat-openc3-command-catalog.md) | Provides the only executable catalog IDs, target/command spellings, args, verifiers, and unresolved boundaries. |
| [T3 operator runbook](./cubesat-openc3-operator-command-runbook.md) | Defines the manual Command Sender smoke path and operator-visible verifier behavior. |
| [T4 automation decision](./cubesat-openc3-automation-decision.md) | Selects Supabase as product I/O, OpenC3 JSON API `cmd` as the bridge command path, and `tlm` polling as verifier path. |
| [T5 bridge contract](./cubesat-openc3-bridge-contract.md) | Defines `cubesat_commands`, `cubesat_command_results`, lifecycle states, result classes, and result payload shape. |
| [T6 telemetry state map](./cubesat-openc3-telemetry-state-map.md) | Defines the logical current-state content written into the bridge-owned latest-state row. |
| [T7 GCP access plan](./cubesat-openc3-gcp-access-plan.md) | Keeps OpenC3/UDP private and limits bridge access to the private VM/network path. |
| [space weather event window migration](../supabase/migrations/20260620225500_create_space_weather_event_windows.sql) | Existing observed-event input table for active/future/ended space-weather windows. |
| [satellite event reports migration](../supabase/migrations/20260621053000_create_satellite_event_reports.sql) | Existing report table that can carry agent evidence, recommendation text, and trace IDs back to event windows. |

External source links are inherited from the linked artifacts, especially the
NOS3 scenarios and OpenC3 JSON API documentation cited in T2 and T4.

## Data Lanes

The first slice must keep five concepts separate:

| Lane | Stored as | May update spacecraft state? | Notes |
| --- | --- | --- | --- |
| Observed space weather | `space_weather_event_windows` and optional `agent_reaction_jobs` | No | Represents SWPC/NOAA-derived event windows and poller dispatch. |
| Simulated spacecraft state | `cubesat_latest_state.state` and `.telemetry` | Yes, when written by the bridge from OpenC3 telemetry | T6 also calls this logical shape `cubesat_state_current`; T5 names the contract table `cubesat_latest_state`. |
| Agent recommendation | `satellite_event_reports.report_json` and later `cubesat_commands.source_trace_id` | No | Text or structured recommendation is evidence only until converted into a catalog command request. |
| Executed simulator command | Manual OpenC3 Command Sender action or bridge-owned OpenC3 JSON API `cmd` | No by itself | Only catalog-resolved target/command/args can be sent by the bridge. |
| Verified result | `cubesat_command_results` plus source-backed latest-state update | Yes, if telemetry samples support it | Result rows follow T5. Manual Command Sender smoke tests do not create bridge result rows unless a future ingestion path is added. |

Common values used in examples:

```json
{
  "satellite_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1",
  "satellite_external_id": "nos3-sim-primary",
  "catalog_version": "nos3-openc3-v1_07_04-cmdcat.20260621",
  "simulator_stack": "nos3_openc3",
  "openc3_scope": "DEFAULT"
}
```

Database-managed timestamps such as `created_at` and `updated_at` are included
where they affect the handoff. Generated UUIDs are stable examples, not reserved
production IDs.

## Scenario 1: Operator Smoke Test, Manual `CFS CFE_ES_NOOP`

Purpose: prove a human operator can reach the private OpenC3 bench, send a
catalogued cFS aliveness command through Command Sender, and confirm telemetry
before trusting automated bridge scenarios.

### Initial Supabase Rows

No event window or agent recommendation is required for this smoke test.
The bridge command queue is intentionally not used:

```json
{
  "table": "cubesat_commands",
  "row": null,
  "reason": "Manual Command Sender smoke test does not enqueue a bridge command."
}
```

The latest known simulator state before the operator action:

```json
{
  "table": "cubesat_latest_state",
  "row": {
    "satellite_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1",
    "simulator_stack": "nos3_openc3",
    "catalog_version": "nos3-openc3-v1_07_04-cmdcat.20260621",
    "openc3_scope": "DEFAULT",
    "state_version": 1200,
    "state": {
      "state_quality": "fresh",
      "orbit": {"in_sun": true},
      "attitude": {"mode": "BDOT", "q_valid": 1, "sun_valid": 1},
      "power": {"battery_voltage_v": 7.91},
      "payload": {"power_state": "ENABLED"},
      "command_counters": {
        "cfs_es": {"cmd_counter": 41, "err_counter": 0}
      },
      "last_command_result": null
    },
    "telemetry": {
      "CFS/CFE_ES_HKPACKET/CMDCOUNTER": {
        "value": 41,
        "type": "CONVERTED",
        "observed_at": "2026-06-21T19:00:02.800Z",
        "source": "openc3_json_api:tlm"
      }
    },
    "fresh_at": "2026-06-21T19:00:02.800Z",
    "stale_after": "2026-06-21T19:00:12.800Z",
    "last_command_id": null,
    "last_result_id": null,
    "last_correlation_id": null,
    "updated_by": "telemetry-publisher-a",
    "updated_at": "2026-06-21T19:00:03.000Z"
  }
}
```

### Current CubeSat State

- Observed space weather: not involved.
- Simulated spacecraft state: cFS housekeeping is fresh and `CMDCOUNTER = 41`.
- Agent recommendation: none.
- Command authority: human operator, private OpenC3 UI only.

### Command Request

Manual OpenC3 action from T3:

```json
{
  "interface": "OpenC3 Command Sender",
  "operator": "bench-operator@example.com",
  "target": "CFS",
  "command": "CFE_ES_NOOP",
  "args": {},
  "sent_from": "private IAP/SSH/VPN browser session",
  "sent_at": "2026-06-21T19:00:03.214Z"
}
```

No bridge `cubesat_commands` row is inserted, and no OpenC3 JSON API call is
made by Soteria for this scenario.

### Catalog Lookup

T2 catalog row:

```json
{
  "catalog_command_id": "cfs_noop",
  "status": "automation_allowed",
  "target": "CFS",
  "command": "CFE_ES_NOOP",
  "args": {},
  "manual_allowed": true,
  "automated_allowed": true,
  "human_review_required": false,
  "verifier": {
    "target": "CFS",
    "packet": "CFE_ES_HKPACKET",
    "item": "CMDCOUNTER",
    "condition": "increments"
  },
  "timeout_seconds": 10,
  "result_classification": "success_when_counter_increments"
}
```

### OpenC3 Call

Manual path: operator selects target `CFS`, packet `CFE_ES_NOOP`, leaves the
generated/default fields unchanged, and sends in Command Sender.

The equivalent structured OpenC3 JSON API shape is shown only for parity with
bridge scenarios:

```json
{
  "jsonrpc": "2.0",
  "method": "cmd",
  "params": ["CFS", "CFE_ES_NOOP", {}],
  "id": "manual_equivalent_noop_001",
  "keyword_params": {"scope": "DEFAULT"}
}
```

### Telemetry Verifier

```json
{
  "target": "CFS",
  "packet": "CFE_ES_HKPACKET",
  "item": "CMDCOUNTER",
  "type": "CONVERTED",
  "condition": "increments",
  "timeout_seconds": 10,
  "before": {
    "value": 41,
    "observed_at": "2026-06-21T19:00:02.800Z",
    "source": "openc3_packet_viewer"
  },
  "after": {
    "value": 42,
    "observed_at": "2026-06-21T19:00:04.118Z",
    "source": "openc3_packet_viewer"
  },
  "status": "satisfied"
}
```

### Final Command Result

Manual smoke result is operator bench evidence, not a T5 bridge result row:

```json
{
  "bridge_result_row": null,
  "manual_result": {
    "status": "succeeded",
    "result_class": "success_when_counter_increments",
    "command_history_line": "CFS CFE_ES_NOOP",
    "verifier": "CFS CFE_ES_HKPACKET CMDCOUNTER 41 -> 42",
    "notes": "No no-check command variants, direct UDP injection, or public OpenC3 URL were used."
  }
}
```

### Final State Update

The telemetry publisher may update the latest-state row from OpenC3 telemetry
after the manual action. Because no bridge result row exists, command/result
foreign-key fields remain null:

```json
{
  "table": "cubesat_latest_state",
  "row": {
    "satellite_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1",
    "simulator_stack": "nos3_openc3",
    "catalog_version": "nos3-openc3-v1_07_04-cmdcat.20260621",
    "openc3_scope": "DEFAULT",
    "state_version": 1201,
    "state": {
      "state_quality": "fresh",
      "command_counters": {
        "cfs_es": {"cmd_counter": 42, "err_counter": 0}
      },
      "last_command_result": null
    },
    "telemetry": {
      "CFS/CFE_ES_HKPACKET/CMDCOUNTER": {
        "value": 42,
        "type": "CONVERTED",
        "observed_at": "2026-06-21T19:00:04.118Z",
        "source": "openc3_json_api:tlm"
      }
    },
    "fresh_at": "2026-06-21T19:00:04.118Z",
    "stale_after": "2026-06-21T19:00:14.118Z",
    "last_command_id": null,
    "last_result_id": null,
    "last_correlation_id": null,
    "updated_by": "telemetry-publisher-a",
    "updated_at": "2026-06-21T19:00:04.500Z"
  }
}
```

### Operator-Visible Behavior

- Command Sender status updates and Command History records `CFS CFE_ES_NOOP`.
- Packet Viewer or Telemetry Viewer shows `CMDCOUNTER` incrementing within
  10 seconds.
- The Soteria operator view can show the refreshed cFS command counter after
  the telemetry publisher writes the latest-state row.
- If the counter does not increment, follow T3 recovery and do not retry with
  no-check or direct UDP paths.

## Scenario 2: Agent Protective Action, Disable Sample Payload

Purpose: prove an AI agent can respond to an active solar-weather event by
submitting a safe source-backed simulator command, while the bridge executes
through OpenC3 and Supabase records the result.

This scenario uses `sample_disable` rather than a generic radiation-protection
command because T2 marks `sample_disable` executable and marks
`radiation_protect_generic` unresolved/rejected.

### Initial Supabase Rows

Observed active space-weather event:

```json
{
  "table": "space_weather_event_windows",
  "row": {
    "id": "10000000-0000-0000-0000-000000000001",
    "event_key": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "event_type": "solar_radiation_storm",
    "source_product": "SWPC proton flux",
    "source_endpoint": "swpc:noaa-scale-or-particle-feed",
    "window_start": "2026-06-21T18:40:00Z",
    "peak_time": "2026-06-21T19:06:00Z",
    "window_end": "2026-06-21T21:30:00Z",
    "peak_value": 110.0,
    "peak_severity": 4,
    "threshold_value": 10.0,
    "units": "pfu",
    "confidence": "observed",
    "status": "active",
    "evidence": {
      "summary": "Observed high proton flux window. Treat as simulator exercise trigger only.",
      "source_links": ["SWPC source recorded by upstream poller"]
    },
    "created_at": "2026-06-21T18:40:20Z",
    "updated_at": "2026-06-21T19:06:15Z"
  }
}
```

Poller dispatch row if `SOTERIA_USE_REACTION_JOBS=true`:

```json
{
  "table": "agent_reaction_jobs",
  "row": {
    "trigger_type": "event_windows_changed",
    "trigger_source": "space_weather_event_windows",
    "source_ids": ["10000000-0000-0000-0000-000000000001"],
    "event_window_ids": ["10000000-0000-0000-0000-000000000001"],
    "priority": "critical",
    "status": "queued",
    "payload": {
      "trigger_type": "event_windows_changed",
      "trigger_source": "space_weather_event_windows",
      "priority": "critical",
      "event_window_ids": ["10000000-0000-0000-0000-000000000001"],
      "event_windows": [
        {
          "event_window_id": "10000000-0000-0000-0000-000000000001",
          "event_key": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
          "event_type": "solar_radiation_storm",
          "source_product": "SWPC proton flux",
          "status": "active",
          "confidence": "observed",
          "priority": "critical",
          "peak_severity": 4,
          "window_start": "2026-06-21T18:40:00Z",
          "window_end": "2026-06-21T21:30:00Z",
          "updated_at": "2026-06-21T19:06:15Z",
          "detected_at": "2026-06-21T19:06:16Z",
          "trigger_source": "space_weather_event_windows"
        }
      ],
      "detected_at": "2026-06-21T19:06:16Z"
    }
  }
}
```

Agent report row carrying the recommendation, not the command authority:

```json
{
  "table": "satellite_event_reports",
  "row": {
    "id": "20000000-0000-0000-0000-000000000001",
    "dedupe_key": "event:10000000-0000-0000-0000-000000000001:nos3-sim-primary:v1",
    "event_window_id": "10000000-0000-0000-0000-000000000001",
    "evidence_hash": "sha256:event-report-sample-disable-001",
    "status": "validated",
    "session_id": "agent-session-solar-001",
    "report_json": {
      "observed_space_weather": {
        "event_window_id": "10000000-0000-0000-0000-000000000001",
        "event_type": "solar_radiation_storm",
        "peak_severity": 4,
        "confidence": "observed"
      },
      "simulated_spacecraft_state_summary": {
        "satellite_external_id": "nos3-sim-primary",
        "payload_power_state": "ENABLED",
        "sample_hk_fresh": true,
        "eps_state_fresh": true
      },
      "agent_recommendation": {
        "intent": "disable_sample_instrument",
        "catalog_command_id": "sample_disable",
        "reason": "Reduce simulator payload activity during the active event without using unresolved radiation-protection commands.",
        "requires_human_review": false
      }
    },
    "failure_json": null,
    "validation_errors": [],
    "created_at": "2026-06-21T19:06:24Z",
    "updated_at": "2026-06-21T19:06:24Z"
  }
}
```

Current simulator state before the command:

```json
{
  "table": "cubesat_latest_state",
  "row": {
    "satellite_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1",
    "simulator_stack": "nos3_openc3",
    "catalog_version": "nos3-openc3-v1_07_04-cmdcat.20260621",
    "openc3_scope": "DEFAULT",
    "state_version": 2210,
    "state": {
      "state_quality": "fresh",
      "orbit": {"in_sun": true},
      "attitude": {"mode": "BDOT", "q_valid": 1, "sun_valid": 1},
      "power": {
        "battery_voltage_v": 7.72,
        "bus_5p0_v": 5.01,
        "switches": {
          "7": {"state": "ON", "current_a": 0.22}
        }
      },
      "payload": {
        "power_state": "ENABLED",
        "device_enabled": "ENABLED",
        "sample_hk_fresh": true
      },
      "fault_flags": {"payload_fault": false, "command_errors": false},
      "command_counters": {
        "sample_radio": {"cmd_count": 17, "cmd_err_count": 0},
        "eps": {"cmd_count": 8, "cmd_err_count": 0}
      },
      "last_command_result": null
    },
    "telemetry": {
      "SAMPLE_RADIO/SAMPLE_HK_TLM/DEVICE_ENABLED": {
        "value": "ENABLED",
        "type": "CONVERTED",
        "observed_at": "2026-06-21T19:06:25Z",
        "source": "openc3_json_api:tlm"
      },
      "SAMPLE_RADIO/SAMPLE_HK_TLM/CMD_COUNT": {
        "value": 17,
        "type": "CONVERTED",
        "observed_at": "2026-06-21T19:06:25Z",
        "source": "openc3_json_api:tlm"
      },
      "GENERIC_EPS/GENERIC_EPS_HK_TLM/BATT_VOLTAGE": {
        "value": 7.72,
        "type": "CONVERTED",
        "observed_at": "2026-06-21T19:06:23Z",
        "source": "openc3_json_api:tlm"
      }
    },
    "fresh_at": "2026-06-21T19:06:25Z",
    "stale_after": "2026-06-21T19:06:40Z",
    "last_command_id": null,
    "last_result_id": null,
    "last_correlation_id": null,
    "updated_by": "telemetry-publisher-a",
    "updated_at": "2026-06-21T19:06:26Z"
  }
}
```

### Current CubeSat State

- Observed space weather: active `solar_radiation_storm`, severity 4,
  confidence `observed`.
- Simulated spacecraft state: sample payload enabled, sample HK fresh, EPS
  telemetry fresh enough for a power-sensitive decision.
- Agent recommendation: request `sample_disable`, not a generic
  radiation-protection command.
- Command authority: bridge only after catalog, source, expiry, idempotency,
  and latest-state guards pass.

### Command Request

The agent or API inserts only the catalog request. It does not provide raw
OpenC3 target or command text:

```json
{
  "table": "cubesat_commands",
  "row": {
    "id": "22222222-2222-2222-2222-222222222222",
    "satellite_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1",
    "satellite_external_id": "nos3-sim-primary",
    "catalog_version": "nos3-openc3-v1_07_04-cmdcat.20260621",
    "catalog_command_id": "sample_disable",
    "args": {},
    "canonical_args_hash": "sha256:44136fa355b3678a1146ad16f7e8649e",
    "idempotency_key": "agent-session-solar-001:event-10000000:sample-disable",
    "source": "ai_agent",
    "source_actor_id": "soteria-agent-sim-v1",
    "source_trace_id": "satellite_event_reports/20000000-0000-0000-0000-000000000001",
    "runbook_id": null,
    "requested_at": "2026-06-21T19:06:30Z",
    "not_before": "2026-06-21T19:06:30Z",
    "expires_at": "2026-06-21T19:08:30Z",
    "status": "queued",
    "priority": 90,
    "required_state_version": 2210,
    "required_state_fresh_after": "2026-06-21T19:06:20Z",
    "approval_id": null,
    "approved_by": null,
    "approved_at": null,
    "correlation_id": "cmdcorr_sample_disable_001",
    "attempt_count": 0,
    "retry_after": null,
    "claimed_by": null,
    "claim_token": null,
    "claimed_at": null,
    "claim_expires_at": null,
    "last_result_id": null,
    "last_error_class": null,
    "created_at": "2026-06-21T19:06:30Z",
    "updated_at": "2026-06-21T19:06:30Z"
  }
}
```

Bridge claim state before send:

```json
{
  "table": "cubesat_commands",
  "row": {
    "id": "22222222-2222-2222-2222-222222222222",
    "status": "accepted",
    "attempt_count": 1,
    "claimed_by": "openc3-bridge-worker-a",
    "claim_token": "22222222-aaaa-bbbb-cccc-222222222222",
    "claimed_at": "2026-06-21T19:06:32Z",
    "claim_expires_at": "2026-06-21T19:08:02Z",
    "updated_at": "2026-06-21T19:06:32Z"
  }
}
```

### Catalog Lookup

```json
{
  "catalog_command_id": "sample_disable",
  "status": "automation_allowed",
  "target": "SAMPLE_RADIO",
  "command": "SAMPLE_DISABLE_CC",
  "args": {},
  "manual_allowed": true,
  "automated_allowed": true,
  "human_review_required": false,
  "preconditions": [
    "target_present:SAMPLE_RADIO",
    "disable_does_not_hide_required_verifier"
  ],
  "verifier": {
    "target": "SAMPLE_RADIO",
    "packet": "SAMPLE_HK_TLM",
    "item": "DEVICE_ENABLED",
    "condition": "equals:DISABLED"
  },
  "timeout_seconds": 15,
  "result_classification": "success_when_disabled",
  "source_doc": "docs/cubesat-openc3-command-catalog.md"
}
```

### OpenC3 Call

The bridge writes send intent, transitions to `running`, then calls OpenC3:

```json
{
  "jsonrpc": "2.0",
  "method": "cmd",
  "params": ["SAMPLE_RADIO", "SAMPLE_DISABLE_CC", {}],
  "id": "cmdexec_sample_disable_001",
  "keyword_params": {"scope": "DEFAULT"}
}
```

Expected OpenC3 response:

```json
{
  "jsonrpc": "2.0",
  "result": ["SAMPLE_RADIO", "SAMPLE_DISABLE_CC", {}],
  "id": "cmdexec_sample_disable_001"
}
```

### Telemetry Verifier

```json
{
  "target": "SAMPLE_RADIO",
  "packet": "SAMPLE_HK_TLM",
  "item": "DEVICE_ENABLED",
  "type": "CONVERTED",
  "condition": "equals:DISABLED",
  "timeout_seconds": 15,
  "polling_rate_seconds": 0.5,
  "before": {
    "value": "ENABLED",
    "observed_at": "2026-06-21T19:06:31.700Z",
    "source": "openc3_json_api:tlm"
  },
  "after": {
    "value": "DISABLED",
    "observed_at": "2026-06-21T19:06:35.200Z",
    "source": "openc3_json_api:tlm"
  },
  "samples": [
    {"value": "ENABLED", "observed_at": "2026-06-21T19:06:33.000Z"},
    {"value": "DISABLED", "observed_at": "2026-06-21T19:06:35.200Z"}
  ],
  "status": "satisfied"
}
```

### Final Command Result

```json
{
  "table": "cubesat_command_results",
  "row": {
    "id": "22222222-2222-2222-2222-000000000101",
    "command_id": "22222222-2222-2222-2222-222222222222",
    "satellite_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1",
    "correlation_id": "cmdcorr_sample_disable_001",
    "execution_id": "cmdexec_sample_disable_001",
    "attempt_number": 1,
    "bridge_worker_id": "openc3-bridge-worker-a",
    "status": "succeeded",
    "result_class": "success_when_disabled",
    "send_outcome": "confirmed",
    "openc3_target": "SAMPLE_RADIO",
    "openc3_command": "SAMPLE_DISABLE_CC",
    "openc3_args": {},
    "sent_at": "2026-06-21T19:06:33.120Z",
    "finished_at": "2026-06-21T19:06:35.450Z",
    "payload": {
      "contract_version": "cubesat-openc3-bridge-contract.v1",
      "command_row_id": "22222222-2222-2222-2222-222222222222",
      "result_row_id": "22222222-2222-2222-2222-000000000101",
      "satellite_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1",
      "correlation_id": "cmdcorr_sample_disable_001",
      "execution_id": "cmdexec_sample_disable_001",
      "attempt_number": 1,
      "idempotency": {
        "idempotency_key": "agent-session-solar-001:event-10000000:sample-disable",
        "catalog_version": "nos3-openc3-v1_07_04-cmdcat.20260621",
        "catalog_command_id": "sample_disable",
        "canonical_args_hash": "sha256:44136fa355b3678a1146ad16f7e8649e"
      },
      "catalog": {
        "simulator_stack": "nos3_openc3",
        "target": "SAMPLE_RADIO",
        "command": "SAMPLE_DISABLE_CC",
        "result_classification": "success_when_disabled",
        "source_doc": "docs/cubesat-openc3-command-catalog.md"
      },
      "openc3": {
        "api": "json_rpc",
        "scope": "DEFAULT",
        "method": "cmd",
        "target": "SAMPLE_RADIO",
        "command": "SAMPLE_DISABLE_CC",
        "args": {},
        "json_rpc_id": "cmdexec_sample_disable_001",
        "send_started_at": "2026-06-21T19:06:33.000Z",
        "sent_at": "2026-06-21T19:06:33.120Z",
        "send_outcome": "confirmed",
        "request": {
          "jsonrpc": "2.0",
          "method": "cmd",
          "params": ["SAMPLE_RADIO", "SAMPLE_DISABLE_CC", {}],
          "id": "cmdexec_sample_disable_001",
          "keyword_params": {"scope": "DEFAULT"}
        },
        "response": {
          "jsonrpc": "2.0",
          "result": ["SAMPLE_RADIO", "SAMPLE_DISABLE_CC", {}],
          "id": "cmdexec_sample_disable_001"
        },
        "error": null
      },
      "telemetry_verifier": {
        "target": "SAMPLE_RADIO",
        "packet": "SAMPLE_HK_TLM",
        "item": "DEVICE_ENABLED",
        "type": "CONVERTED",
        "condition": "equals:DISABLED",
        "timeout_seconds": 15,
        "polling_rate_seconds": 0.5,
        "before": {
          "value": "ENABLED",
          "observed_at": "2026-06-21T19:06:31.700Z",
          "source": "openc3_json_api:tlm"
        },
        "after": {
          "value": "DISABLED",
          "observed_at": "2026-06-21T19:06:35.200Z",
          "source": "openc3_json_api:tlm"
        },
        "samples": [
          {"value": "ENABLED", "observed_at": "2026-06-21T19:06:33.000Z"},
          {"value": "DISABLED", "observed_at": "2026-06-21T19:06:35.200Z"}
        ],
        "status": "satisfied"
      },
      "state_updates": [
        {
          "table": "cubesat_latest_state",
          "state_path": "payload.device_enabled",
          "before": "ENABLED",
          "after": "DISABLED",
          "state_version_after": 2211
        },
        {
          "table": "cubesat_latest_state",
          "state_path": "command_counters.sample_radio.cmd_count",
          "before": 17,
          "after": 18,
          "state_version_after": 2211
        }
      ],
      "logs": {
        "bridge_log_pointer": "gcp-log://soteria-openc3-bridge/cmdcorr_sample_disable_001",
        "openc3_command_log_pointer": "openc3://cmd-history/SAMPLE_RADIO/SAMPLE_DISABLE_CC/cmdexec_sample_disable_001",
        "telemetry_window_pointer": "openc3://tlm/SAMPLE_RADIO/SAMPLE_HK_TLM/DEVICE_ENABLED?from=2026-06-21T19:06:31Z&to=2026-06-21T19:06:36Z"
      }
    },
    "created_at": "2026-06-21T19:06:35.460Z"
  }
}
```

The bridge also sets the command row to terminal success:

```json
{
  "table": "cubesat_commands",
  "row": {
    "id": "22222222-2222-2222-2222-222222222222",
    "status": "succeeded",
    "last_result_id": "22222222-2222-2222-2222-000000000101",
    "last_error_class": null,
    "updated_at": "2026-06-21T19:06:35.470Z"
  }
}
```

### Final State Update

```json
{
  "table": "cubesat_latest_state",
  "row": {
    "satellite_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1",
    "simulator_stack": "nos3_openc3",
    "catalog_version": "nos3-openc3-v1_07_04-cmdcat.20260621",
    "openc3_scope": "DEFAULT",
    "state_version": 2211,
    "state": {
      "state_quality": "partial",
      "quality_reasons": [
        "sample data packets may become stale after payload disable; sample HK remains fresh"
      ],
      "orbit": {"in_sun": true},
      "attitude": {"mode": "BDOT", "q_valid": 1, "sun_valid": 1},
      "power": {"battery_voltage_v": 7.73},
      "payload": {
        "power_state": "DISABLED",
        "device_enabled": "DISABLED",
        "sample_hk_fresh": true,
        "sample_data_expected_stale": true
      },
      "fault_flags": {"payload_fault": false, "command_errors": false},
      "command_counters": {
        "sample_radio": {"cmd_count": 18, "cmd_err_count": 0}
      },
      "last_command_result": {
        "command_id": "22222222-2222-2222-2222-222222222222",
        "result_id": "22222222-2222-2222-2222-000000000101",
        "catalog_command_id": "sample_disable",
        "status": "succeeded",
        "result_class": "success_when_disabled",
        "completed_at": "2026-06-21T19:06:35.450Z"
      }
    },
    "telemetry": {
      "SAMPLE_RADIO/SAMPLE_HK_TLM/DEVICE_ENABLED": {
        "value": "DISABLED",
        "type": "CONVERTED",
        "observed_at": "2026-06-21T19:06:35.200Z",
        "source": "openc3_json_api:tlm"
      },
      "SAMPLE_RADIO/SAMPLE_HK_TLM/CMD_COUNT": {
        "value": 18,
        "type": "CONVERTED",
        "observed_at": "2026-06-21T19:06:35.200Z",
        "source": "openc3_json_api:tlm"
      }
    },
    "fresh_at": "2026-06-21T19:06:35.200Z",
    "stale_after": "2026-06-21T19:06:50.200Z",
    "last_command_id": "22222222-2222-2222-2222-222222222222",
    "last_result_id": "22222222-2222-2222-2222-000000000101",
    "last_correlation_id": "cmdcorr_sample_disable_001",
    "updated_by": "openc3-bridge-worker-a",
    "updated_at": "2026-06-21T19:06:35.500Z"
  }
}
```

### Operator-Visible Behavior

- Soteria event view shows an active observed solar-weather event.
- The report/recommendation view shows `sample_disable` as the concrete
  catalogued action and explicitly rejects generic radiation-protection action.
- Command timeline shows `queued -> accepted -> running -> succeeded`.
- OpenC3 Command History records `SAMPLE_RADIO SAMPLE_DISABLE_CC`.
- Telemetry panel shows `SAMPLE_RADIO SAMPLE_HK_TLM DEVICE_ENABLED` changing
  from `ENABLED` to `DISABLED`.

## Scenario 3: Rejected Command, Generic EPS Load Shed Policy Unresolved

Purpose: prove the bridge rejects an agent request when the desired operational
intent is not yet mapped to a safe catalog command. T2 found the exact
`GENERIC_EPS GENERIC_EPS_SWITCH_CC` command for switch-level manual control,
but generic load-to-switch policy remains unresolved.

### Initial Supabase Rows

Observed event:

```json
{
  "table": "space_weather_event_windows",
  "row": {
    "id": "30000000-0000-0000-0000-000000000001",
    "event_key": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "event_type": "geomagnetic_storm",
    "source_product": "SWPC geomagnetic scale",
    "source_endpoint": "swpc:noaa-scale-or-kp-feed",
    "window_start": "2026-06-21T20:00:00Z",
    "peak_time": "2026-06-21T20:25:00Z",
    "window_end": "2026-06-21T23:30:00Z",
    "peak_value": 8.0,
    "peak_severity": 3,
    "threshold_value": 5.0,
    "units": "Kp",
    "confidence": "observed",
    "status": "active",
    "evidence": {
      "summary": "Observed geomagnetic storm exercise window. Agent may recommend conservative power posture, but EPS load shed policy is unresolved."
    },
    "created_at": "2026-06-21T20:00:15Z",
    "updated_at": "2026-06-21T20:25:10Z"
  }
}
```

Agent report recommends a generic load shed but records the unresolved policy
boundary:

```json
{
  "table": "satellite_event_reports",
  "row": {
    "id": "30000000-0000-0000-0000-000000000201",
    "dedupe_key": "event:30000000-0000-0000-0000-000000000001:nos3-sim-primary:v1",
    "event_window_id": "30000000-0000-0000-0000-000000000001",
    "evidence_hash": "sha256:event-report-eps-reject-001",
    "status": "validated_with_unresolved_action",
    "session_id": "agent-session-geomag-001",
    "report_json": {
      "observed_space_weather": {
        "event_window_id": "30000000-0000-0000-0000-000000000001",
        "event_type": "geomagnetic_storm",
        "peak_severity": 3,
        "confidence": "observed"
      },
      "simulated_spacecraft_state_summary": {
        "battery_voltage_v": 7.02,
        "eps_switches_fresh": true,
        "switch_7_state": "ON"
      },
      "agent_recommendation": {
        "intent": "generic_eps_load_shed",
        "catalog_command_id": "eps_load_shed_policy",
        "reason": "Power posture recommendation cannot select a load because no approved load-to-switch policy exists.",
        "expected_bridge_outcome": "rejected"
      }
    },
    "failure_json": null,
    "validation_errors": [],
    "created_at": "2026-06-21T20:25:22Z",
    "updated_at": "2026-06-21T20:25:22Z"
  }
}
```

Latest state before rejection:

```json
{
  "table": "cubesat_latest_state",
  "row": {
    "satellite_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1",
    "simulator_stack": "nos3_openc3",
    "catalog_version": "nos3-openc3-v1_07_04-cmdcat.20260621",
    "openc3_scope": "DEFAULT",
    "state_version": 2300,
    "state": {
      "state_quality": "fresh",
      "power": {
        "battery_voltage_v": 7.02,
        "bus_5p0_v": 4.99,
        "switches": {
          "0": {"state": "ON", "current_a": 0.07},
          "7": {"state": "ON", "current_a": 0.24}
        }
      },
      "payload": {"device_enabled": "ENABLED"},
      "fault_flags": {"eps_switch_faults": false},
      "command_counters": {
        "eps": {"cmd_count": 8, "cmd_err_count": 0}
      },
      "last_command_result": {
        "catalog_command_id": "sample_disable",
        "status": "succeeded",
        "result_class": "success_when_disabled"
      }
    },
    "telemetry": {
      "GENERIC_EPS/GENERIC_EPS_HK_TLM/BATT_VOLTAGE": {
        "value": 7.02,
        "type": "CONVERTED",
        "observed_at": "2026-06-21T20:25:20Z",
        "source": "openc3_json_api:tlm"
      },
      "GENERIC_EPS/GENERIC_EPS_HK_TLM/SWITCH_7_STATE": {
        "value": "ON",
        "type": "CONVERTED",
        "observed_at": "2026-06-21T20:25:20Z",
        "source": "openc3_json_api:tlm"
      },
      "GENERIC_EPS/GENERIC_EPS_HK_TLM/SW_7_CURRENT": {
        "value": 0.24,
        "type": "CONVERTED",
        "observed_at": "2026-06-21T20:25:20Z",
        "source": "openc3_json_api:tlm"
      }
    },
    "fresh_at": "2026-06-21T20:25:20Z",
    "stale_after": "2026-06-21T20:25:30Z",
    "last_command_id": "22222222-2222-2222-2222-222222222222",
    "last_result_id": "22222222-2222-2222-2222-000000000101",
    "last_correlation_id": "cmdcorr_sample_disable_001",
    "updated_by": "telemetry-publisher-a",
    "updated_at": "2026-06-21T20:25:21Z"
  }
}
```

### Current CubeSat State

- Observed space weather: active geomagnetic storm exercise.
- Simulated spacecraft state: EPS telemetry is fresh and switch 7 is ON.
- Agent recommendation: generic EPS load shed, not a specific switch command.
- Executable boundary: `eps_switch7_off_manual` exists for manual low-power
  scenario switch 7 only, but `eps_load_shed_policy` is unresolved and must not
  substitute a switch number automatically.

### Command Request

The request is allowed into the queue only as a catalog ID for audit; it is
expected to be rejected before any OpenC3 send:

```json
{
  "table": "cubesat_commands",
  "row": {
    "id": "33333333-3333-3333-3333-333333333333",
    "satellite_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1",
    "satellite_external_id": "nos3-sim-primary",
    "catalog_version": "nos3-openc3-v1_07_04-cmdcat.20260621",
    "catalog_command_id": "eps_load_shed_policy",
    "args": {"load": "payload"},
    "canonical_args_hash": "sha256:example-eps-load-payload",
    "idempotency_key": "agent-session-geomag-001:event-30000000:eps-load-shed",
    "source": "ai_agent",
    "source_actor_id": "soteria-agent-sim-v1",
    "source_trace_id": "satellite_event_reports/30000000-0000-0000-0000-000000000201",
    "runbook_id": null,
    "requested_at": "2026-06-21T20:25:30Z",
    "not_before": "2026-06-21T20:25:30Z",
    "expires_at": "2026-06-21T20:27:30Z",
    "status": "queued",
    "priority": 80,
    "required_state_version": 2300,
    "required_state_fresh_after": "2026-06-21T20:25:15Z",
    "approval_id": null,
    "approved_by": null,
    "approved_at": null,
    "correlation_id": "cmdcorr_eps_reject_001",
    "attempt_count": 0,
    "retry_after": null,
    "claimed_by": null,
    "claim_token": null,
    "claimed_at": null,
    "claim_expires_at": null,
    "last_result_id": null,
    "last_error_class": null,
    "created_at": "2026-06-21T20:25:30Z",
    "updated_at": "2026-06-21T20:25:30Z"
  }
}
```

### Catalog Lookup

```json
{
  "catalog_command_id": "eps_load_shed_policy",
  "status": "unresolved",
  "target": null,
  "command": null,
  "args": [],
  "manual_allowed": false,
  "automated_allowed": false,
  "human_review_required": true,
  "preconditions": ["blocked_until_load_to_switch_policy_exists"],
  "verifier": null,
  "timeout_seconds": null,
  "result_classification": "blocked_unresolved_mapping",
  "important_boundary": "Do not substitute GENERIC_EPS GENERIC_EPS_SWITCH_CC unless an approved load-to-switch policy selects the exact SWITCH_NUMBER and restore rules."
}
```

### OpenC3 Call

No OpenC3 call is allowed:

```json
{
  "openc3_call": null,
  "send_outcome": "not_sent",
  "reason": "Catalog entry is unresolved and lacks target, command, args, verifier, and timeout."
}
```

### Telemetry Verifier

No command verifier is evaluated because no command was sent:

```json
{
  "telemetry_verifier": null,
  "reason": "unresolved_catalog_entry before send"
}
```

### Final Command Result

```json
{
  "table": "cubesat_command_results",
  "row": {
    "id": "33333333-3333-3333-3333-000000000101",
    "command_id": "33333333-3333-3333-3333-333333333333",
    "satellite_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1",
    "correlation_id": "cmdcorr_eps_reject_001",
    "execution_id": "cmdexec_eps_reject_001",
    "attempt_number": 1,
    "bridge_worker_id": "openc3-bridge-worker-a",
    "status": "rejected",
    "result_class": "unresolved_catalog_entry",
    "send_outcome": "not_sent",
    "openc3_target": null,
    "openc3_command": null,
    "openc3_args": {},
    "sent_at": null,
    "finished_at": "2026-06-21T20:25:32.200Z",
    "payload": {
      "contract_version": "cubesat-openc3-bridge-contract.v1",
      "command_row_id": "33333333-3333-3333-3333-333333333333",
      "result_row_id": "33333333-3333-3333-3333-000000000101",
      "satellite_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1",
      "correlation_id": "cmdcorr_eps_reject_001",
      "execution_id": "cmdexec_eps_reject_001",
      "attempt_number": 1,
      "idempotency": {
        "idempotency_key": "agent-session-geomag-001:event-30000000:eps-load-shed",
        "catalog_version": "nos3-openc3-v1_07_04-cmdcat.20260621",
        "catalog_command_id": "eps_load_shed_policy",
        "canonical_args_hash": "sha256:example-eps-load-payload"
      },
      "catalog": {
        "simulator_stack": "nos3_openc3",
        "catalog_command_id": "eps_load_shed_policy",
        "status": "unresolved",
        "target": null,
        "command": null,
        "result_classification": "blocked_unresolved_mapping",
        "source_doc": "docs/cubesat-openc3-command-catalog.md"
      },
      "openc3": {
        "api": "json_rpc",
        "scope": "DEFAULT",
        "method": "cmd",
        "target": null,
        "command": null,
        "args": {},
        "json_rpc_id": "cmdexec_eps_reject_001",
        "send_started_at": null,
        "sent_at": null,
        "send_outcome": "not_sent",
        "request": null,
        "response": null,
        "error": {
          "class": "unresolved_catalog_entry",
          "message": "Generic EPS load shed has no approved load-to-switch policy.",
          "retryable": false
        }
      },
      "telemetry_verifier": null,
      "state_updates": [],
      "logs": {
        "bridge_log_pointer": "gcp-log://soteria-openc3-bridge/cmdcorr_eps_reject_001",
        "openc3_command_log_pointer": null,
        "telemetry_window_pointer": null
      }
    },
    "created_at": "2026-06-21T20:25:32.210Z"
  }
}
```

Command row terminal update:

```json
{
  "table": "cubesat_commands",
  "row": {
    "id": "33333333-3333-3333-3333-333333333333",
    "status": "rejected",
    "last_result_id": "33333333-3333-3333-3333-000000000101",
    "last_error_class": "unresolved_catalog_entry",
    "updated_at": "2026-06-21T20:25:32.220Z"
  }
}
```

### Final State Update

No spacecraft state update occurs. The rejection result is an audit record, not
OpenC3 telemetry:

```json
{
  "table": "cubesat_latest_state",
  "row": "unchanged",
  "reason": "No OpenC3 command was sent and no verifier telemetry supports a spacecraft-state change."
}
```

### Operator-Visible Behavior

- Soteria command timeline shows `queued -> accepted -> rejected`.
- UI reason is `unresolved_catalog_entry`.
- Operator sees that `GENERIC_EPS GENERIC_EPS_SWITCH_CC` exists only as
  switch-level manual evidence for `eps_switch7_off_manual`, not as generic
  load shedding.
- OpenC3 Command History has no new EPS command for this request.
- The next action is manual review or a future load-to-switch policy task, not
  automatic retry.

## Scenario 4: Verification Timeout, ADCS Sun-Safe Requested

Purpose: prove the bridge can record a command that was confirmed sent by
OpenC3 but failed its telemetry verifier. This is the required verification
timeout case.

This scenario uses `adcs_set_sunsafe`, which T2 marks
`automation_allowed_with_review`. The agent may recommend it, but the bridge
must require valid operator approval before sending.

### Initial Supabase Rows

Observed event and agent report:

```json
{
  "table": "space_weather_event_windows",
  "row": {
    "id": "40000000-0000-0000-0000-000000000001",
    "event_key": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
    "event_type": "radio_blackout",
    "source_product": "SWPC radio blackout scale",
    "source_endpoint": "swpc:noaa-scale-or-xray-feed",
    "window_start": "2026-06-21T21:00:00Z",
    "peak_time": "2026-06-21T21:10:00Z",
    "window_end": "2026-06-21T22:00:00Z",
    "peak_value": 3.0,
    "peak_severity": 3,
    "threshold_value": 1.0,
    "units": "NOAA R scale",
    "confidence": "observed",
    "status": "active",
    "evidence": {
      "summary": "Exercise window for attitude-protective recommendation. Stock NOS3 does not prove space-weather physics, only command and verifier mechanics."
    },
    "created_at": "2026-06-21T21:00:05Z",
    "updated_at": "2026-06-21T21:10:05Z"
  }
}
```

```json
{
  "table": "satellite_event_reports",
  "row": {
    "id": "40000000-0000-0000-0000-000000000201",
    "dedupe_key": "event:40000000-0000-0000-0000-000000000001:nos3-sim-primary:v1",
    "event_window_id": "40000000-0000-0000-0000-000000000001",
    "evidence_hash": "sha256:event-report-adcs-sunsafe-001",
    "status": "validated",
    "session_id": "agent-session-radio-001",
    "report_json": {
      "observed_space_weather": {
        "event_window_id": "40000000-0000-0000-0000-000000000001",
        "event_type": "radio_blackout",
        "peak_severity": 3,
        "confidence": "observed"
      },
      "simulated_spacecraft_state_summary": {
        "attitude_mode": "BDOT",
        "sun_valid": 1,
        "adcs_hk_fresh": true
      },
      "agent_recommendation": {
        "intent": "set_adcs_sunsafe",
        "catalog_command_id": "adcs_set_sunsafe",
        "reason": "Demonstrate reviewed ADCS protective posture command in simulator.",
        "requires_human_review": true
      }
    },
    "failure_json": null,
    "validation_errors": [],
    "created_at": "2026-06-21T21:10:16Z",
    "updated_at": "2026-06-21T21:10:16Z"
  }
}
```

Current state before send:

```json
{
  "table": "cubesat_latest_state",
  "row": {
    "satellite_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1",
    "simulator_stack": "nos3_openc3",
    "catalog_version": "nos3-openc3-v1_07_04-cmdcat.20260621",
    "openc3_scope": "DEFAULT",
    "state_version": 2400,
    "state": {
      "state_quality": "fresh",
      "orbit": {"in_sun": true},
      "attitude": {
        "mode": "BDOT",
        "q_valid": 1,
        "sun_valid": 1,
        "body_rate_rad_s": [0.001, 0.002, -0.001]
      },
      "power": {"battery_voltage_v": 7.84},
      "fault_flags": {"invalid_attitude_solution": false},
      "command_counters": {
        "adcs": {"cmd_count": 12, "cmd_err_count": 0}
      },
      "last_command_result": null
    },
    "telemetry": {
      "GENERIC_ADCS/GENERIC_ADCS_GNC/MODE": {
        "value": "BDOT",
        "type": "CONVERTED",
        "observed_at": "2026-06-21T21:10:18Z",
        "source": "openc3_json_api:tlm"
      },
      "GENERIC_ADCS/GENERIC_ADCS_GNC/SUN_VALID": {
        "value": 1,
        "type": "CONVERTED",
        "observed_at": "2026-06-21T21:10:18Z",
        "source": "openc3_json_api:tlm"
      },
      "GENERIC_ADCS/GENERIC_ADCS_HK_TLM/CMD_COUNT": {
        "value": 12,
        "type": "CONVERTED",
        "observed_at": "2026-06-21T21:10:18Z",
        "source": "openc3_json_api:tlm"
      }
    },
    "fresh_at": "2026-06-21T21:10:18Z",
    "stale_after": "2026-06-21T21:10:23Z",
    "last_command_id": null,
    "last_result_id": null,
    "last_correlation_id": null,
    "updated_by": "telemetry-publisher-a",
    "updated_at": "2026-06-21T21:10:18.500Z"
  }
}
```

### Current CubeSat State

- Observed space weather: active exercise event for radio blackout.
- Simulated spacecraft state: ADCS telemetry is fresh, `MODE = BDOT`,
  `SUN_VALID = 1`.
- Agent recommendation: `adcs_set_sunsafe`.
- Operator review: required and present before the bridge can send.

### Command Request

```json
{
  "table": "cubesat_commands",
  "row": {
    "id": "44444444-4444-4444-4444-444444444444",
    "satellite_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1",
    "satellite_external_id": "nos3-sim-primary",
    "catalog_version": "nos3-openc3-v1_07_04-cmdcat.20260621",
    "catalog_command_id": "adcs_set_sunsafe",
    "args": {"GNC_MODE": "SUNSAFE_MODE"},
    "canonical_args_hash": "sha256:example-adcs-sunsafe",
    "idempotency_key": "agent-session-radio-001:event-40000000:adcs-sunsafe",
    "source": "ai_agent",
    "source_actor_id": "soteria-agent-sim-v1",
    "source_trace_id": "satellite_event_reports/40000000-0000-0000-0000-000000000201",
    "runbook_id": null,
    "requested_at": "2026-06-21T21:10:20Z",
    "not_before": "2026-06-21T21:10:20Z",
    "expires_at": "2026-06-21T21:12:20Z",
    "status": "queued",
    "priority": 85,
    "required_state_version": 2400,
    "required_state_fresh_after": "2026-06-21T21:10:15Z",
    "approval_id": "approval-adcs-sunsafe-001",
    "approved_by": "bench-operator@example.com",
    "approved_at": "2026-06-21T21:10:35Z",
    "correlation_id": "cmdcorr_adcs_timeout_001",
    "attempt_count": 0,
    "retry_after": null,
    "claimed_by": null,
    "claim_token": null,
    "claimed_at": null,
    "claim_expires_at": null,
    "last_result_id": null,
    "last_error_class": null,
    "created_at": "2026-06-21T21:10:20Z",
    "updated_at": "2026-06-21T21:10:35Z"
  }
}
```

### Catalog Lookup

```json
{
  "catalog_command_id": "adcs_set_sunsafe",
  "status": "automation_allowed_with_review",
  "target": "GENERIC_ADCS",
  "command": "GENERIC_ADCS_SET_MODE_CC",
  "args": {"GNC_MODE": "SUNSAFE_MODE"},
  "manual_allowed": true,
  "automated_allowed": true,
  "human_review_required": true,
  "preconditions": [
    "target_present:GENERIC_ADCS",
    "operator_accepts_sunsafe_mode"
  ],
  "verifier": {
    "target": "GENERIC_ADCS",
    "packet": "GENERIC_ADCS_GNC",
    "item": "MODE",
    "condition": "equals:SUNSAFE"
  },
  "timeout_seconds": 45,
  "result_classification": "success_when_mode_sunsafe"
}
```

### OpenC3 Call

```json
{
  "jsonrpc": "2.0",
  "method": "cmd",
  "params": [
    "GENERIC_ADCS",
    "GENERIC_ADCS_SET_MODE_CC",
    {"GNC_MODE": "SUNSAFE_MODE"}
  ],
  "id": "cmdexec_adcs_timeout_001",
  "keyword_params": {"scope": "DEFAULT"}
}
```

Expected OpenC3 response before verifier failure:

```json
{
  "jsonrpc": "2.0",
  "result": [
    "GENERIC_ADCS",
    "GENERIC_ADCS_SET_MODE_CC",
    {"GNC_MODE": "SUNSAFE_MODE"}
  ],
  "id": "cmdexec_adcs_timeout_001"
}
```

### Telemetry Verifier

The command response is confirmed, but `MODE` never becomes `SUNSAFE` before
the 45 second timeout:

```json
{
  "target": "GENERIC_ADCS",
  "packet": "GENERIC_ADCS_GNC",
  "item": "MODE",
  "type": "CONVERTED",
  "condition": "equals:SUNSAFE",
  "timeout_seconds": 45,
  "polling_rate_seconds": 0.5,
  "before": {
    "value": "BDOT",
    "observed_at": "2026-06-21T21:10:34.900Z",
    "source": "openc3_json_api:tlm"
  },
  "after": {
    "value": "BDOT",
    "observed_at": "2026-06-21T21:11:20.200Z",
    "source": "openc3_json_api:tlm"
  },
  "samples": [
    {"value": "BDOT", "observed_at": "2026-06-21T21:10:40.000Z"},
    {"value": "BDOT", "observed_at": "2026-06-21T21:10:55.000Z"},
    {"value": "BDOT", "observed_at": "2026-06-21T21:11:10.000Z"},
    {"value": "BDOT", "observed_at": "2026-06-21T21:11:20.200Z"}
  ],
  "status": "timeout"
}
```

### Final Command Result

```json
{
  "table": "cubesat_command_results",
  "row": {
    "id": "44444444-4444-4444-4444-000000000101",
    "command_id": "44444444-4444-4444-4444-444444444444",
    "satellite_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1",
    "correlation_id": "cmdcorr_adcs_timeout_001",
    "execution_id": "cmdexec_adcs_timeout_001",
    "attempt_number": 1,
    "bridge_worker_id": "openc3-bridge-worker-a",
    "status": "failed",
    "result_class": "telemetry_verifier_timeout",
    "send_outcome": "confirmed",
    "openc3_target": "GENERIC_ADCS",
    "openc3_command": "GENERIC_ADCS_SET_MODE_CC",
    "openc3_args": {"GNC_MODE": "SUNSAFE_MODE"},
    "sent_at": "2026-06-21T21:10:36.100Z",
    "finished_at": "2026-06-21T21:11:20.300Z",
    "payload": {
      "contract_version": "cubesat-openc3-bridge-contract.v1",
      "command_row_id": "44444444-4444-4444-4444-444444444444",
      "result_row_id": "44444444-4444-4444-4444-000000000101",
      "satellite_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1",
      "correlation_id": "cmdcorr_adcs_timeout_001",
      "execution_id": "cmdexec_adcs_timeout_001",
      "attempt_number": 1,
      "idempotency": {
        "idempotency_key": "agent-session-radio-001:event-40000000:adcs-sunsafe",
        "catalog_version": "nos3-openc3-v1_07_04-cmdcat.20260621",
        "catalog_command_id": "adcs_set_sunsafe",
        "canonical_args_hash": "sha256:example-adcs-sunsafe"
      },
      "catalog": {
        "simulator_stack": "nos3_openc3",
        "target": "GENERIC_ADCS",
        "command": "GENERIC_ADCS_SET_MODE_CC",
        "result_classification": "success_when_mode_sunsafe",
        "source_doc": "docs/cubesat-openc3-command-catalog.md"
      },
      "openc3": {
        "api": "json_rpc",
        "scope": "DEFAULT",
        "method": "cmd",
        "target": "GENERIC_ADCS",
        "command": "GENERIC_ADCS_SET_MODE_CC",
        "args": {"GNC_MODE": "SUNSAFE_MODE"},
        "json_rpc_id": "cmdexec_adcs_timeout_001",
        "send_started_at": "2026-06-21T21:10:36.000Z",
        "sent_at": "2026-06-21T21:10:36.100Z",
        "send_outcome": "confirmed",
        "request": {
          "jsonrpc": "2.0",
          "method": "cmd",
          "params": [
            "GENERIC_ADCS",
            "GENERIC_ADCS_SET_MODE_CC",
            {"GNC_MODE": "SUNSAFE_MODE"}
          ],
          "id": "cmdexec_adcs_timeout_001",
          "keyword_params": {"scope": "DEFAULT"}
        },
        "response": {
          "jsonrpc": "2.0",
          "result": [
            "GENERIC_ADCS",
            "GENERIC_ADCS_SET_MODE_CC",
            {"GNC_MODE": "SUNSAFE_MODE"}
          ],
          "id": "cmdexec_adcs_timeout_001"
        },
        "error": null
      },
      "telemetry_verifier": {
        "target": "GENERIC_ADCS",
        "packet": "GENERIC_ADCS_GNC",
        "item": "MODE",
        "type": "CONVERTED",
        "condition": "equals:SUNSAFE",
        "timeout_seconds": 45,
        "polling_rate_seconds": 0.5,
        "before": {
          "value": "BDOT",
          "observed_at": "2026-06-21T21:10:34.900Z",
          "source": "openc3_json_api:tlm"
        },
        "after": {
          "value": "BDOT",
          "observed_at": "2026-06-21T21:11:20.200Z",
          "source": "openc3_json_api:tlm"
        },
        "samples": [
          {"value": "BDOT", "observed_at": "2026-06-21T21:10:40.000Z"},
          {"value": "BDOT", "observed_at": "2026-06-21T21:10:55.000Z"},
          {"value": "BDOT", "observed_at": "2026-06-21T21:11:10.000Z"},
          {"value": "BDOT", "observed_at": "2026-06-21T21:11:20.200Z"}
        ],
        "status": "timeout"
      },
      "state_updates": [
        {
          "table": "cubesat_latest_state",
          "state_path": "attitude.mode",
          "before": "BDOT",
          "after": "BDOT",
          "state_version_after": 2401
        },
        {
          "table": "cubesat_latest_state",
          "state_path": "last_command_result",
          "before": null,
          "after": {
            "catalog_command_id": "adcs_set_sunsafe",
            "status": "failed",
            "result_class": "telemetry_verifier_timeout"
          },
          "state_version_after": 2401
        }
      ],
      "logs": {
        "bridge_log_pointer": "gcp-log://soteria-openc3-bridge/cmdcorr_adcs_timeout_001",
        "openc3_command_log_pointer": "openc3://cmd-history/GENERIC_ADCS/GENERIC_ADCS_SET_MODE_CC/cmdexec_adcs_timeout_001",
        "telemetry_window_pointer": "openc3://tlm/GENERIC_ADCS/GENERIC_ADCS_GNC/MODE?from=2026-06-21T21:10:34Z&to=2026-06-21T21:11:21Z"
      }
    },
    "created_at": "2026-06-21T21:11:20.310Z"
  }
}
```

Command row terminal update:

```json
{
  "table": "cubesat_commands",
  "row": {
    "id": "44444444-4444-4444-4444-444444444444",
    "status": "failed",
    "last_result_id": "44444444-4444-4444-4444-000000000101",
    "last_error_class": "telemetry_verifier_timeout",
    "updated_at": "2026-06-21T21:11:20.320Z"
  }
}
```

### Final State Update

The state row records the source-backed fact that ADCS mode remained `BDOT` and
the latest command result failed. It must not claim sun-safe was achieved:

```json
{
  "table": "cubesat_latest_state",
  "row": {
    "satellite_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaa1",
    "simulator_stack": "nos3_openc3",
    "catalog_version": "nos3-openc3-v1_07_04-cmdcat.20260621",
    "openc3_scope": "DEFAULT",
    "state_version": 2401,
    "state": {
      "state_quality": "fresh",
      "orbit": {"in_sun": true},
      "attitude": {
        "mode": "BDOT",
        "q_valid": 1,
        "sun_valid": 1
      },
      "fault_flags": {
        "invalid_attitude_solution": false,
        "command_errors": false
      },
      "command_counters": {
        "adcs": {"cmd_count": 13, "cmd_err_count": 0}
      },
      "last_command_result": {
        "command_id": "44444444-4444-4444-4444-444444444444",
        "result_id": "44444444-4444-4444-4444-000000000101",
        "catalog_command_id": "adcs_set_sunsafe",
        "status": "failed",
        "result_class": "telemetry_verifier_timeout",
        "completed_at": "2026-06-21T21:11:20.300Z"
      }
    },
    "telemetry": {
      "GENERIC_ADCS/GENERIC_ADCS_GNC/MODE": {
        "value": "BDOT",
        "type": "CONVERTED",
        "observed_at": "2026-06-21T21:11:20.200Z",
        "source": "openc3_json_api:tlm"
      },
      "GENERIC_ADCS/GENERIC_ADCS_HK_TLM/CMD_COUNT": {
        "value": 13,
        "type": "CONVERTED",
        "observed_at": "2026-06-21T21:11:20.000Z",
        "source": "openc3_json_api:tlm"
      }
    },
    "fresh_at": "2026-06-21T21:11:20.200Z",
    "stale_after": "2026-06-21T21:11:25.200Z",
    "last_command_id": "44444444-4444-4444-4444-444444444444",
    "last_result_id": "44444444-4444-4444-4444-000000000101",
    "last_correlation_id": "cmdcorr_adcs_timeout_001",
    "updated_by": "openc3-bridge-worker-a",
    "updated_at": "2026-06-21T21:11:20.350Z"
  }
}
```

### Operator-Visible Behavior

- Soteria shows the reviewed AI recommendation and operator approval.
- Command timeline shows `queued -> accepted -> running -> failed`.
- Failure class is `telemetry_verifier_timeout`, not `rejected`.
- OpenC3 Command History shows the ADCS command was sent.
- Telemetry view shows `GENERIC_ADCS GENERIC_ADCS_GNC MODE` stayed `BDOT`;
  Soteria does not claim the spacecraft entered sun-safe.
- Operator next step is investigation or manual OpenC3/T3 recovery, not an
  automatic resend.

## Tabletop Validation

Executable-command mapping against T2:

| Scenario | Catalog ID | Executable OpenC3 command | Validation |
| --- | --- | --- | --- |
| Operator smoke | `cfs_noop` | `CFS` / `CFE_ES_NOOP` | Present in T2 and T3; manual allowed and automated allowed. |
| Agent sample disable | `sample_disable` | `SAMPLE_RADIO` / `SAMPLE_DISABLE_CC` | Present in T2; automated allowed; verifier `DEVICE_ENABLED == DISABLED`. |
| EPS load shed rejection | `eps_load_shed_policy` | none | T2 status `unresolved`; bridge must reject and must not substitute `GENERIC_EPS_SWITCH_CC`. |
| ADCS timeout | `adcs_set_sunsafe` | `GENERIC_ADCS` / `GENERIC_ADCS_SET_MODE_CC` with `GNC_MODE=SUNSAFE_MODE` | Present in T2; automated allowed with human review; timeout uses T5 `telemetry_verifier_timeout`. |

Result-field mapping against T5:

| Field family | Covered in scenarios |
| --- | --- |
| Command lifecycle | `queued`, `accepted`, `running` implied before send, `succeeded`, `rejected`, and `failed`. |
| Result classes | `success_when_disabled`, `unresolved_catalog_entry`, and `telemetry_verifier_timeout`. Manual smoke uses operator evidence rather than a T5 result row. |
| Send outcomes | `confirmed` and `not_sent`. |
| OpenC3 fields | `openc3_target`, `openc3_command`, `openc3_args`, `sent_at`, `method=cmd`, JSON-RPC request/response. |
| Verifier fields | target, packet, item, type, condition, timeout, polling rate, before/after samples, status. |
| State updates | Success updates payload state; rejection leaves state unchanged; timeout records telemetry-supported unchanged ADCS mode and failed last result. |
| Bypass prevention | No agent row contains raw executable target/command. Bridge resolves target/command only from catalog. |

Manual and automated coverage:

- Manual OpenC3/COSMOS 5 Command Sender use is shown in Scenario 1.
- Automated bridge use through Supabase and OpenC3 JSON API is shown in
  Scenarios 2, 3, and 4.
- A rejected command is shown in Scenario 3.
- A verification timeout after confirmed send is shown in Scenario 4.

## Implementation Checklist For Future Agents

- Create migrations for `cubesat_commands`, `cubesat_command_results`, and
  `cubesat_latest_state` following T5 before coding the bridge.
- Keep `target`, `command`, `command_string`, OpenC3 URL, and tokens out of
  agent-writable command request rows.
- Add an enqueue RPC that validates `catalog_command_id`, computes
  `canonical_args_hash`, enforces idempotency, and stores `source_trace_id`.
- Implement bridge claim/recovery with `FOR UPDATE SKIP LOCKED`,
  `claim_token`, and no resend after send intent.
- Implement catalog lookup from the pinned T2 catalog version.
- Implement OpenC3 JSON API `cmd` only, with `keyword_params.scope=DEFAULT`.
- Implement verifier polling through OpenC3 `tlm` or equivalent structured
  telemetry reads.
- Write result rows before and after send as T5 requires; never drop ambiguous
  or timeout cases.
- Publish latest state only from OpenC3 telemetry samples and bridge-owned
  result summaries.
- Add UI labels that separate observed event, simulated state, agent
  recommendation, executed command, and verified result.
- Add a manual-review path for `automation_allowed_with_review` commands such
  as `adcs_set_sunsafe`.
- Keep the EPS load-shed request rejected until a load-to-switch policy maps
  loads to exact `SWITCH_NUMBER`, allowed states, restore order, and thresholds.

## Remaining Risks

- Stock NOS3 may not model the physical space-weather effects implied by the
  event type; these scenarios prove command mechanics and data lineage, not
  space-weather physics.
- `agent_reaction_jobs` is a poller design path, but its migration was not part
  of the reviewed schema. Treat that row as optional until schema ownership is
  settled.
- Manual Command Sender smoke results are not T5 bridge result rows. A future
  operator-evidence table or manual ingestion path is needed if the product must
  audit manual sends in Supabase with the same rigor as bridge sends.
- ADCS `SUNSAFE` timeout behavior must be verified on a running NOS3 bench; the
  row examples are tabletop expectations.
- State field spelling must remain tied to T6 extracted telemetry names. Unknown
  OpenC3 target, packet, or item names are blockers, not guessable fields.
