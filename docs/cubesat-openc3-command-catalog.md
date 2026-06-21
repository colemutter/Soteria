# CubeSat OpenC3/NOS3 Command Catalog

Generated: 2026-06-21

Recommended catalog version: `nos3-openc3-v1_07_04-cmdcat.20260621`

This catalog maps Soteria simulator intents to source-backed NOS3/OpenC3
commands. Every row is for the NOS3/OpenC3 simulator stack only. Nothing here
is a flight command, flight rule, spacecraft procedure, command authority, RF
uplink path, or claim of flight qualification.

## Version And Extraction Basis

| Field | Value |
| --- | --- |
| `catalog_version` | `nos3-openc3-v1_07_04-cmdcat.20260621` |
| `simulator_stack` | `nos3_openc3` |
| NOS3 release/tag | `v1_07_04` / release `1.7.4` |
| NOS3 commit | `4428de566833527c49b16d322157ed11ad8f2318` |
| Extraction method | Shallow clone of the official NOS3 tag into `/private/tmp`, then selective submodule checkout for COSMOS/OpenC3 target files and component command dictionaries. |
| Local checkout status | The Soteria workspace did not contain a NOS3 checkout. The catalog was extracted from the official NOS3 tag and pinned submodules, not from a persistent repo-local NOS3 tree. |
| Manual command path | OpenC3/COSMOS Command Sender using private access to the NOS3 bench. |
| Automation path | Future Soteria bridge through OpenC3 only after target/command/args/verifier checks pass. |

Pinned submodules used for command evidence:

| Submodule | Commit |
| --- | --- |
| `gsw/cosmos` | `caeef73bd65b45d5396974cf010d18139ef773fa` |
| `components/sample` | `9d1a76dc391fefe7a42314052c1f10fa527f526b` |
| `components/generic_adcs` | `01a2088629a3b05332c2457e5df8ec3d0eaceb30` |
| `components/generic_reaction_wheel` | `22c3c4c313d81465797a57d845b3729a236c0254` |
| `components/generic_eps` | `1aad19930ada314091d5be0b75bfd4379a39765d` |
| `components/generic_radio` | `687db4817499e5e617aac2b75b89f89f22624c56` |
| `components/mgr` | `e4f56752df4549ffe074b79d768374f51099357b` |

OpenC3 target aliases are defined in `gsw/cosmos/config/system/stash/system.txt`.
Important aliases for this catalog include `CFS_RADIO`, `SAMPLE_RADIO`,
`MGR_RADIO`, and `SIM_CMDBUS_BRIDGE`. The seed name
`SIM_CMD_BUS_BRIDGE` is a documentation spelling in the NOS3 scenario text;
the command dictionary target is `SIM_CMDBUS_BRIDGE`.

## Catalog Policy

| Policy | Rule |
| --- | --- |
| Simulator-only | All rows are scoped to stock NOS3 + OpenC3/COSMOS 5. |
| Exact spelling | Executable rows use target and command spellings from scenario docs plus target dictionaries. |
| Hidden cFS fields | CCSDS header/checksum fields are dictionary fields but are ignored by the OpenC3 target configuration and are not bridge input args. |
| Automation | `automated_allowed = true` means the future bridge may execute after allowlist, precondition, idempotency, expiry, and verifier checks. |
| Review | `human_review_required = true` means automation can draft or stage the command but should not send it without an operator approval step. |
| Manual-only | `automated_allowed = false` with `status = manual_only` means keep the command in Command Sender/operator procedures for now. |
| Unresolved | `status = unresolved` means do not execute or generate copy-pasteable OpenC3 commands from Soteria for that intent. |

## Command Catalog

Every row below has `catalog_version =
nos3-openc3-v1_07_04-cmdcat.20260621`, `simulator_stack =
nos3_openc3`, `nos3_version = 1.7.4`, `nos3_tag = v1_07_04`, and
`nos3_commit = 4428de566833527c49b16d322157ed11ad8f2318`.

| ID | Status | Intent | OpenC3 target / command | Typed args and allowed values | Manual allowed | Automated allowed | Human review | Preconditions | Verifier telemetry | Timeout | Result classification | Source evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `cfs_noop` | `automation_allowed` | Connectivity check / cFS aliveness | `CFS` / `CFE_ES_NOOP` | none; OpenC3 supplies ignored CCSDS fields | yes | yes | no | OpenC3 target list contains `CFS`; cFS telemetry fresh enough to compare counters | `CFS CFE_ES_HKPACKET CMDCOUNTER` increments, or FSW console NOOP event appears | 10s | `success_when_counter_increments`; `failed_no_counter`; `failed_cmd_error` | NOS3 demo scenario; `gsw/cosmos/config/targets/CFS/cmd_tlm/ES.txt`; `gsw/cosmos/config/targets/CFS/cmd_tlm/ES_TLM.txt`; `gsw/LPT.ycs` |
| `radio_enable_output` | `automation_allowed` | Enable radio telemetry output | `CFS_RADIO` / `TO_ENABLE_OUTPUT` | `DEST_IP`: string, default and approved value `radio-sim`; `DEST_PORT`: uint16, approved value `5011` | yes | yes | no for bench smoke; yes if used to change a long-running test posture | `CFS_RADIO` alias present; radio path private; destination matches NOS3 bench network; no public OpenC3/UDP exposure | `CFS_RADIO TO_HKPACKET ENABLEDROUTES` changes or radio packets become fresh; Command and Telemetry Server byte counters increase | 10s | `success_when_radio_tlm_fresh`; `failed_no_fresh_tlm`; `blocked_bad_destination` | NOS3 commissioning scenario; NOS3 ground software; `gsw/cosmos/config/system/stash/system.txt`; `gsw/cosmos/config/targets/CFS/cmd_tlm/TO.txt`; `TO_TLM.txt` |
| `radio_resume_output` | `automation_allowed` | Resume paused radio telemetry output | `CFS_RADIO` / `TO_RESUME_OUTPUT` | none; OpenC3 supplies ignored CCSDS fields | yes | yes | no | Radio output previously enabled or paused; `CFS_RADIO` telemetry expected | `CFS_RADIO TO_HKPACKET CMDCOUNTER` increments and telemetry packets become fresh | 10s | `success_when_radio_tlm_resumes`; `failed_no_counter`; `failed_no_fresh_tlm` | NOS3 commissioning scenario; `gsw/cosmos/config/targets/CFS/cmd_tlm/TO.txt`; `TO_TLM.txt` |
| `radio_disable_output` | `automation_allowed` | Disable radio telemetry output for low-power/comm posture demo | `CFS_RADIO` / `TO_DISABLE_OUTPUT` | none; OpenC3 supplies ignored CCSDS fields | yes | yes | yes outside smoke tests | Operator confirms telemetry loss is acceptable; bridge has alternate health path or expected outage window | `CFS_RADIO TO_HKPACKET CMDCOUNTER` increments, `ENABLEDROUTES` changes, and radio telemetry output stops or goes stale as expected | 10s | `success_when_output_stops`; `failed_counter_not_incremented`; `failed_unexpected_tlm_loss` | NOS3 commissioning scenario; `gsw/cosmos/config/targets/CFS/cmd_tlm/TO.txt`; `TO_TLM.txt` |
| `sample_noop` | `automation_allowed` | Sample payload app aliveness | `SAMPLE` / `SAMPLE_NOOP_CC` | none; OpenC3 supplies ignored CCSDS fields | yes | yes | no | `SAMPLE` target present; sample HK telemetry visible or requestable | `SAMPLE SAMPLE_HK_TLM CMD_COUNT` increments; `CMD_ERR_COUNT` unchanged | 10s | `success_when_counter_increments`; `failed_no_counter`; `failed_cmd_error` | NOS3 demo scenario; `components/sample/gsw/SAMPLE/cmd_tlm/SAMPLE_CMD.txt`; `SAMPLE_TLM.txt`; `gsw/LPT.ycs`; `NOS_SAMPLE_APP.opi` |
| `sample_enable` | `automation_allowed` | Enable sample instrument/device | `SAMPLE_RADIO` / `SAMPLE_ENABLE_CC` | none; OpenC3 supplies ignored CCSDS fields | yes | yes | no for demo setup; yes in power-constrained scenarios | `SAMPLE_RADIO` alias present; enabling payload is allowed by current scenario; power margin acceptable for demo | `SAMPLE_RADIO SAMPLE_HK_TLM DEVICE_ENABLED == ENABLED`, `CMD_COUNT` increments, sample data becomes fresh | 15s | `success_when_enabled`; `failed_not_enabled`; `failed_cmd_error` | NOS3 commissioning scenario; `gsw/cosmos/config/system/stash/system.txt`; `components/sample/gsw/SAMPLE/cmd_tlm/SAMPLE_CMD.txt`; `SAMPLE_TLM.txt`; `NOS_SAMPLE_APP.opi` |
| `sample_disable` | `automation_allowed` | Disable sample instrument/device | `SAMPLE_RADIO` / `SAMPLE_DISABLE_CC` | none; OpenC3 supplies ignored CCSDS fields | yes | yes | no for demo payload standby; yes if part of broader safe-mode plan | `SAMPLE_RADIO` alias present; disabling does not hide required verifier telemetry for the test | `SAMPLE_RADIO SAMPLE_HK_TLM DEVICE_ENABLED == DISABLED`, `CMD_COUNT` increments, sample data may stop or become stale | 15s | `success_when_disabled`; `failed_still_enabled`; `failed_cmd_error` | NOS3 commissioning scenario; `gsw/cosmos/config/system/stash/system.txt`; `components/sample/gsw/SAMPLE/cmd_tlm/SAMPLE_CMD.txt`; `SAMPLE_TLM.txt`; `NOS_SAMPLE_APP.opi` |
| `sample_sim_set_status` | `manual_only` | Inject sample simulator device status/fault | `SIM_CMDBUS_BRIDGE` / `SAMPLE_SIM_SET_STATUS` | `STATUS`: uint32, `MIN_UINT32..MAX_UINT32`; scenario value `5` demonstrates a status error; no bridge default | yes | no | yes | Operator is intentionally running a fault-injection scenario; sample target visible; baseline status captured | `SAMPLE SAMPLE_HK_TLM DEVICE_STATUS` changes to requested status; FSW event/log reports status error when applicable | 15s | `success_when_status_matches`; `manual_fault_injected`; `failed_no_status_change` | NOS3 demo scenario; `components/sample/gsw/SAMPLE_SIM_CMD.txt`; `components/sample/gsw/SAMPLE/lib/sample_lib.rb`; `SAMPLE_TLM.txt`; target alias in `system.txt` |
| `adcs_set_passive` | `automation_allowed_with_review` | Set ADCS passive mode | `GENERIC_ADCS` / `GENERIC_ADCS_SET_MODE_CC` | `GNC_MODE`: uint8 enum `PASSIVE=0`, `BDOT_MODE=1`, `SUNSAFE_MODE=2`, `INERTIAL_MODE=3`; use `PASSIVE` | yes | yes | yes | Operator/bridge confirms this is a simulator attitude test; no pending command expects ADCS to hold sun-safe; 42/ADCS telemetry visible | `GENERIC_ADCS GENERIC_ADCS_GNC MODE == PASSIVE`; `GENERIC_ADCS_HK_TLM CMD_COUNT` increments; 42 visual may show tumbling | 30s | `success_when_mode_passive`; `failed_mode_mismatch`; `review_required` | NOS3 demo scenario; `components/generic_adcs/gsw/GENERIC_ADCS/cmd_tlm/GENERIC_ADCS_CMD.txt`; `GENERIC_ADCS_TLM.txt`; `generic_adcs_lib.rb` |
| `adcs_set_sunsafe` | `automation_allowed_with_review` | Set ADCS sun-safe mode | `GENERIC_ADCS` / `GENERIC_ADCS_SET_MODE_CC` | `GNC_MODE`: uint8 enum `PASSIVE=0`, `BDOT_MODE=1`, `SUNSAFE_MODE=2`, `INERTIAL_MODE=3`; use `SUNSAFE_MODE` | yes | yes | yes | Sun vector/sensor validity is adequate for the scenario, or the operator accepts the demo limitation; ADCS target visible | `GENERIC_ADCS GENERIC_ADCS_GNC MODE == SUNSAFE`; `GENERIC_ADCS_HK_TLM CMD_COUNT` increments; 42 visual shows sun-safe pointing when in sun | 45s | `success_when_mode_sunsafe`; `failed_mode_mismatch`; `review_required` | NOS3 demo scenario; `components/generic_adcs/gsw/GENERIC_ADCS/cmd_tlm/GENERIC_ADCS_CMD.txt`; `GENERIC_ADCS_TLM.txt`; `generic_adcs_lib.rb` |
| `rw_set_torque` | `manual_only` | Reaction wheel torque demo command template | `GENERIC_REACTION_WHEEL` / `GENERIC_RW_SET_TORQUE_CC` | `WHEEL_NUMBER`: uint8 `0..2`; `TORQUE`: int16 `MIN_INT16..MAX_INT16`, units `1e-4 N-m`; no Soteria default torque | yes | no | yes | ADCS passive or otherwise not fighting wheel commands; operator chooses wheel and torque; test duration bounded | `GENERIC_REACTION_WHEEL GENRW_HK_TLM_T COMMAND_COUNT` increments; `MOMENTUM_NMS_0/1/2` changes for selected wheel; 42 attitude response may be visible | 30s | `success_when_momentum_changes`; `manual_attitude_effect`; `failed_no_momentum_change` | NOS3 demo scenario; `components/generic_reaction_wheel/gsw/GENERIC_REACTION_WHEEL/cmd_tlm/GENERIC_REACTION_WHEEL_CMD.txt`; `GENERIC_REACTION_WHEEL_TLM.txt`; `generic_reaction_wheel_lib.rb` |
| `mgr_set_ak_enable` | `automation_allowed_with_review` | Enable Alaska science region configuration | `MGR_RADIO` / `MGR_SET_AK_CC` | `AK_STATUS`: uint8 enum `DISABLE=0`, `ENABLE=1`; use `ENABLE` | yes | yes | yes | Commissioning/science configuration context; `MGR_RADIO` alias present; operator allows science-region config | `MGR_RADIO MGR_HK_TLM AK_CONFIG == ENABLED`; `CMD_COUNT` increments | 15s | `success_when_ak_enabled`; `failed_ak_not_enabled`; `review_required` | NOS3 commissioning scenario; `gsw/cosmos/config/system/stash/system.txt`; `components/mgr/gsw/MGR/cmd_tlm/MGR_CMD.txt`; `MGR_TLM.txt` |
| `eps_switch7_off_manual` | `manual_only` | Manual low-power scenario switch-off evidence, not generic load-shed policy | `GENERIC_EPS` / `GENERIC_EPS_SWITCH_CC` | `SWITCH_NUMBER`: uint8 enum `SWITCH_0..SWITCH_7` (`0x00..0x07`) plus `UNDEFINED=0xFF`; use `SWITCH_7` only for the NOS3 low-power scenario; `STATE`: uint8 enum `OFF=0x00`, `ON=0xAA`; use `OFF` | yes | no | yes | Low-power scenario reproduced; switch 7 verified unexpectedly on; operator confirms target switch is nonessential in this scenario; EPS telemetry visible | `GENERIC_EPS GENERIC_EPS_HK_TLM SWITCH_7_STATE == OFF`; `SW_7_CURRENT` decreases; `CMD_COUNT` increments | 20s | `success_when_switch7_off`; `manual_power_triage`; `failed_switch_still_on` | NOS3 low-power scenario; `components/generic_eps/gsw/GENERIC_EPS/cmd_tlm/GENERIC_EPS_CMD.txt`; `GENERIC_EPS_TLM.txt`; `gsw/cosmos/procedures/PassSetupEPSCheck_LowPowerScen.rb` |
| `eps_load_shed_policy` | `unresolved` | Generic Soteria EPS load shed intent | unresolved | unresolved; do not substitute a switch id without a scenario/procedure-specific load map | no | no | yes | Blocked until a Soteria/NOS3 load-shed policy maps loads to switch numbers and defines restore order | Blocker: no approved load selection rule. Candidate telemetry after resolution: `GENERIC_EPS_HK_TLM SWITCH_n_STATE`, `SW_n_CURRENT`, bus/battery voltage/current fields | n/a | `blocked_unresolved_mapping` | Exact EPS switch command exists, but the generic load-shed intent remains unresolved because choosing which load to shed is a policy/procedure decision. |
| `radiation_protect_generic` | `unresolved_rejected` | Generic Soteria radiation-protection command | none | none | no | no | yes | Rejected because no NOS3/OpenC3 target/command maps this generic operation to a source-backed simulator command | Explicit blocker; requires future component or approved procedure | n/a | `blocked_no_nos3_target` | Local `docs/satellite-command-tool-mapping.md` says exact commands must come from a mission command source; no matching NOS3 target found. |

## Unresolved Command List

| Intent | Status | Reason | Next evidence needed |
| --- | --- | --- | --- |
| Generic EPS load shed | unresolved | The exact `GENERIC_EPS GENERIC_EPS_SWITCH_CC` dictionary exists, and the low-power scenario identifies switch 7 as the manual triage case. Soteria still lacks an approved load-to-switch policy for choosing arbitrary shed loads, so the generic intent must not automate. | A Soteria/NOS3 procedure that maps each load to `SWITCH_NUMBER`, allowed power states, restore order, and telemetry thresholds. |
| Generic radiation protection | rejected/unresolved | No stock NOS3/OpenC3 target or command was found for a generic `radiation_protect` operation. | Future simulator component or source-backed procedure that defines concrete commands and telemetry verifiers. |
| Future compute-payload commands | unresolved | `JOB_START`, `JOB_PAUSE`, `JOB_CHECKPOINT`, and `SET_CPU_LIMIT` do not exist in stock NOS3. | Implement and dictionary-publish a NOS3 compute-payload component before making these executable. |

## Validation Performed

1. Cross-checked `CFS_RADIO TO_ENABLE_OUTPUT` against the NOS3 commissioning scenario and `TO.txt`. The dictionary requires `DEST_IP` string and `DEST_PORT` uint16; the scenario uses `radio-sim` and `5011`.
2. Cross-checked `SAMPLE_RADIO SAMPLE_ENABLE_CC` and `SAMPLE_RADIO SAMPLE_DISABLE_CC` against the commissioning scenario, `system.txt` target aliases, and `SAMPLE_CMD.txt`/`SAMPLE_TLM.txt`.
3. Cross-checked `GENERIC_ADCS GENERIC_ADCS_SET_MODE_CC` against the demonstration scenario and `GENERIC_ADCS_CMD.txt`. Allowed `GNC_MODE` states are `PASSIVE`, `BDOT_MODE`, `SUNSAFE_MODE`, and `INERTIAL_MODE`.
4. Cross-checked reaction wheel torque args against `GENERIC_REACTION_WHEEL_CMD.txt`; the catalog does not invent a default wheel or torque.
5. Rejected `radiation_protect_generic` because no NOS3/OpenC3 target/command was found for that generic Soteria command family.

## Source Links

- [NOS3 repository release/tag basis](https://github.com/nasa/nos3)
- [NOS3 Demonstration Scenario](https://nos3.readthedocs.io/en/latest/Scenario_Demo.html)
- [NOS3 Commissioning Scenario](https://nos3.readthedocs.io/en/latest/Scenario_Commissioning.html)
- [NOS3 Low Power Scenario](https://nos3.readthedocs.io/en/latest/Scenario_Low_Power.html)
- [NOS3 Ground Software](https://nos3.readthedocs.io/en/latest/NOS3_Ground_Software.html)
- [OpenC3 Command Sender](https://docs.openc3.com/docs/tools/cmd-sender)
- [OpenC3 COSMOS and NASA cFS guide](https://docs.openc3.com/docs/guides/cfs)
- [NOS3 target alias declarations](https://github.com/nasa-itc/gsw-cosmos/blob/caeef73bd65b45d5396974cf010d18139ef773fa/config/system/stash/system.txt)
- [OpenC3 CFS ES command definitions](https://github.com/nasa-itc/gsw-cosmos/blob/caeef73bd65b45d5396974cf010d18139ef773fa/config/targets/CFS/cmd_tlm/ES.txt)
- [OpenC3 CFS TO command definitions](https://github.com/nasa-itc/gsw-cosmos/blob/caeef73bd65b45d5396974cf010d18139ef773fa/config/targets/CFS/cmd_tlm/TO.txt)
- [OpenC3 CFS ES telemetry definitions](https://github.com/nasa-itc/gsw-cosmos/blob/caeef73bd65b45d5396974cf010d18139ef773fa/config/targets/CFS/cmd_tlm/ES_TLM.txt)
- [OpenC3 CFS TO telemetry definitions](https://github.com/nasa-itc/gsw-cosmos/blob/caeef73bd65b45d5396974cf010d18139ef773fa/config/targets/CFS/cmd_tlm/TO_TLM.txt)
- [Sample command definitions](https://github.com/nasa-itc/sample/blob/9d1a76dc391fefe7a42314052c1f10fa527f526b/gsw/SAMPLE/cmd_tlm/SAMPLE_CMD.txt)
- [Sample telemetry definitions](https://github.com/nasa-itc/sample/blob/9d1a76dc391fefe7a42314052c1f10fa527f526b/gsw/SAMPLE/cmd_tlm/SAMPLE_TLM.txt)
- [Sample simulator command definitions](https://github.com/nasa-itc/sample/blob/9d1a76dc391fefe7a42314052c1f10fa527f526b/gsw/SAMPLE_SIM_CMD.txt)
- [Generic ADCS command definitions](https://github.com/nasa-itc/generic_adcs/blob/01a2088629a3b05332c2457e5df8ec3d0eaceb30/gsw/GENERIC_ADCS/cmd_tlm/GENERIC_ADCS_CMD.txt)
- [Generic ADCS telemetry definitions](https://github.com/nasa-itc/generic_adcs/blob/01a2088629a3b05332c2457e5df8ec3d0eaceb30/gsw/GENERIC_ADCS/cmd_tlm/GENERIC_ADCS_TLM.txt)
- [Generic reaction wheel command definitions](https://github.com/nasa-itc/generic_reaction_wheel/blob/22c3c4c313d81465797a57d845b3729a236c0254/gsw/GENERIC_REACTION_WHEEL/cmd_tlm/GENERIC_REACTION_WHEEL_CMD.txt)
- [Generic reaction wheel telemetry definitions](https://github.com/nasa-itc/generic_reaction_wheel/blob/22c3c4c313d81465797a57d845b3729a236c0254/gsw/GENERIC_REACTION_WHEEL/cmd_tlm/GENERIC_REACTION_WHEEL_TLM.txt)
- [Generic EPS command definitions](https://github.com/nasa-itc/generic_eps/blob/1aad19930ada314091d5be0b75bfd4379a39765d/gsw/GENERIC_EPS/cmd_tlm/GENERIC_EPS_CMD.txt)
- [Generic EPS telemetry definitions](https://github.com/nasa-itc/generic_eps/blob/1aad19930ada314091d5be0b75bfd4379a39765d/gsw/GENERIC_EPS/cmd_tlm/GENERIC_EPS_TLM.txt)
- [MGR command definitions](https://github.com/nasa-itc/mgr/blob/e4f56752df4549ffe074b79d768374f51099357b/gsw/MGR/cmd_tlm/MGR_CMD.txt)
- [MGR telemetry definitions](https://github.com/nasa-itc/mgr/blob/e4f56752df4549ffe074b79d768374f51099357b/gsw/MGR/cmd_tlm/MGR_TLM.txt)

## Machine-Readable Appendix

```json
{
  "catalog_version": "nos3-openc3-v1_07_04-cmdcat.20260621",
  "simulator_stack": "nos3_openc3",
  "nos3": {
    "release": "1.7.4",
    "tag": "v1_07_04",
    "commit": "4428de566833527c49b16d322157ed11ad8f2318",
    "source": "https://github.com/nasa/nos3"
  },
  "submodules": {
    "gsw/cosmos": "caeef73bd65b45d5396974cf010d18139ef773fa",
    "components/sample": "9d1a76dc391fefe7a42314052c1f10fa527f526b",
    "components/generic_adcs": "01a2088629a3b05332c2457e5df8ec3d0eaceb30",
    "components/generic_reaction_wheel": "22c3c4c313d81465797a57d845b3729a236c0254",
    "components/generic_eps": "1aad19930ada314091d5be0b75bfd4379a39765d",
    "components/mgr": "e4f56752df4549ffe074b79d768374f51099357b"
  },
  "record_defaults": {
    "catalog_version": "nos3-openc3-v1_07_04-cmdcat.20260621",
    "simulator_stack": "nos3_openc3",
    "nos3_version": "1.7.4",
    "nos3_tag": "v1_07_04",
    "nos3_commit": "4428de566833527c49b16d322157ed11ad8f2318"
  },
  "commands": [
    {
      "id": "cfs_noop",
      "status": "automation_allowed",
      "simulator_only": true,
      "target": "CFS",
      "command": "CFE_ES_NOOP",
      "args": [],
      "intent": "connectivity_check",
      "manual_allowed": true,
      "automated_allowed": true,
      "human_review_required": false,
      "preconditions": ["target_present:CFS", "telemetry_available:CFS/CFE_ES_HKPACKET/CMDCOUNTER"],
      "verifier": {"target": "CFS", "packet": "CFE_ES_HKPACKET", "item": "CMDCOUNTER", "condition": "increments"},
      "timeout_seconds": 10,
      "result_classification": "success_when_counter_increments"
    },
    {
      "id": "radio_enable_output",
      "status": "automation_allowed",
      "simulator_only": true,
      "target": "CFS_RADIO",
      "command": "TO_ENABLE_OUTPUT",
      "args": [
        {"name": "DEST_IP", "type": "STRING", "allowed_values": ["radio-sim"], "default": "radio-sim"},
        {"name": "DEST_PORT", "type": "UINT16", "allowed_values": [5011], "default": 5011}
      ],
      "intent": "enable_radio_telemetry",
      "manual_allowed": true,
      "automated_allowed": true,
      "human_review_required": false,
      "preconditions": ["target_present:CFS_RADIO", "private_radio_path", "dest_matches_nos3_bench"],
      "verifier": {"target": "CFS_RADIO", "packet": "TO_HKPACKET", "item": "ENABLEDROUTES", "condition": "changes_or_radio_packets_fresh"},
      "timeout_seconds": 10,
      "result_classification": "success_when_radio_tlm_fresh"
    },
    {
      "id": "radio_resume_output",
      "status": "automation_allowed",
      "simulator_only": true,
      "target": "CFS_RADIO",
      "command": "TO_RESUME_OUTPUT",
      "args": [],
      "intent": "resume_radio_telemetry",
      "manual_allowed": true,
      "automated_allowed": true,
      "human_review_required": false,
      "preconditions": ["target_present:CFS_RADIO", "radio_output_previously_enabled_or_paused"],
      "verifier": {"target": "CFS_RADIO", "packet": "TO_HKPACKET", "item": "CMDCOUNTER", "condition": "increments_and_packets_fresh"},
      "timeout_seconds": 10,
      "result_classification": "success_when_radio_tlm_resumes"
    },
    {
      "id": "radio_disable_output",
      "status": "automation_allowed",
      "simulator_only": true,
      "target": "CFS_RADIO",
      "command": "TO_DISABLE_OUTPUT",
      "args": [],
      "intent": "disable_radio_telemetry",
      "manual_allowed": true,
      "automated_allowed": true,
      "human_review_required": true,
      "preconditions": ["target_present:CFS_RADIO", "operator_accepts_expected_telemetry_loss"],
      "verifier": {"target": "CFS_RADIO", "packet": "TO_HKPACKET", "item": "CMDCOUNTER", "condition": "increments_and_output_stops"},
      "timeout_seconds": 10,
      "result_classification": "success_when_output_stops"
    },
    {
      "id": "sample_noop",
      "status": "automation_allowed",
      "simulator_only": true,
      "target": "SAMPLE",
      "command": "SAMPLE_NOOP_CC",
      "args": [],
      "intent": "sample_payload_noop",
      "manual_allowed": true,
      "automated_allowed": true,
      "human_review_required": false,
      "preconditions": ["target_present:SAMPLE", "telemetry_available:SAMPLE/SAMPLE_HK_TLM/CMD_COUNT"],
      "verifier": {"target": "SAMPLE", "packet": "SAMPLE_HK_TLM", "item": "CMD_COUNT", "condition": "increments"},
      "timeout_seconds": 10,
      "result_classification": "success_when_counter_increments"
    },
    {
      "id": "sample_enable",
      "status": "automation_allowed",
      "simulator_only": true,
      "target": "SAMPLE_RADIO",
      "command": "SAMPLE_ENABLE_CC",
      "args": [],
      "intent": "enable_sample_instrument",
      "manual_allowed": true,
      "automated_allowed": true,
      "human_review_required": false,
      "preconditions": ["target_present:SAMPLE_RADIO", "scenario_allows_payload_enable"],
      "verifier": {"target": "SAMPLE_RADIO", "packet": "SAMPLE_HK_TLM", "item": "DEVICE_ENABLED", "condition": "equals:ENABLED"},
      "timeout_seconds": 15,
      "result_classification": "success_when_enabled"
    },
    {
      "id": "sample_disable",
      "status": "automation_allowed",
      "simulator_only": true,
      "target": "SAMPLE_RADIO",
      "command": "SAMPLE_DISABLE_CC",
      "args": [],
      "intent": "disable_sample_instrument",
      "manual_allowed": true,
      "automated_allowed": true,
      "human_review_required": false,
      "preconditions": ["target_present:SAMPLE_RADIO", "disable_does_not_hide_required_verifier"],
      "verifier": {"target": "SAMPLE_RADIO", "packet": "SAMPLE_HK_TLM", "item": "DEVICE_ENABLED", "condition": "equals:DISABLED"},
      "timeout_seconds": 15,
      "result_classification": "success_when_disabled"
    },
    {
      "id": "sample_sim_set_status",
      "status": "manual_only",
      "simulator_only": true,
      "target": "SIM_CMDBUS_BRIDGE",
      "command": "SAMPLE_SIM_SET_STATUS",
      "args": [{"name": "STATUS", "type": "UINT32", "min": 0, "max": 4294967295, "scenario_example": 5}],
      "intent": "inject_sample_device_fault",
      "manual_allowed": true,
      "automated_allowed": false,
      "human_review_required": true,
      "preconditions": ["fault_injection_scenario_active", "baseline_sample_status_captured"],
      "verifier": {"target": "SAMPLE", "packet": "SAMPLE_HK_TLM", "item": "DEVICE_STATUS", "condition": "equals_requested_STATUS"},
      "timeout_seconds": 15,
      "result_classification": "manual_fault_injected"
    },
    {
      "id": "adcs_set_passive",
      "status": "automation_allowed_with_review",
      "simulator_only": true,
      "target": "GENERIC_ADCS",
      "command": "GENERIC_ADCS_SET_MODE_CC",
      "args": [{"name": "GNC_MODE", "type": "UINT8_ENUM", "allowed_values": {"PASSIVE": 0, "BDOT_MODE": 1, "SUNSAFE_MODE": 2, "INERTIAL_MODE": 3}, "value": "PASSIVE"}],
      "intent": "set_adcs_passive",
      "manual_allowed": true,
      "automated_allowed": true,
      "human_review_required": true,
      "preconditions": ["simulator_attitude_test_active", "operator_accepts_passive_mode"],
      "verifier": {"target": "GENERIC_ADCS", "packet": "GENERIC_ADCS_GNC", "item": "MODE", "condition": "equals:PASSIVE"},
      "timeout_seconds": 30,
      "result_classification": "success_when_mode_passive"
    },
    {
      "id": "adcs_set_sunsafe",
      "status": "automation_allowed_with_review",
      "simulator_only": true,
      "target": "GENERIC_ADCS",
      "command": "GENERIC_ADCS_SET_MODE_CC",
      "args": [{"name": "GNC_MODE", "type": "UINT8_ENUM", "allowed_values": {"PASSIVE": 0, "BDOT_MODE": 1, "SUNSAFE_MODE": 2, "INERTIAL_MODE": 3}, "value": "SUNSAFE_MODE"}],
      "intent": "set_adcs_sunsafe",
      "manual_allowed": true,
      "automated_allowed": true,
      "human_review_required": true,
      "preconditions": ["target_present:GENERIC_ADCS", "operator_accepts_sunsafe_mode"],
      "verifier": {"target": "GENERIC_ADCS", "packet": "GENERIC_ADCS_GNC", "item": "MODE", "condition": "equals:SUNSAFE"},
      "timeout_seconds": 45,
      "result_classification": "success_when_mode_sunsafe"
    },
    {
      "id": "rw_set_torque",
      "status": "manual_only",
      "simulator_only": true,
      "target": "GENERIC_REACTION_WHEEL",
      "command": "GENERIC_RW_SET_TORQUE_CC",
      "args": [
        {"name": "WHEEL_NUMBER", "type": "UINT8", "min": 0, "max": 2},
        {"name": "TORQUE", "type": "INT16", "units": "1e-4 N-m", "min": -32768, "max": 32767}
      ],
      "intent": "reaction_wheel_torque_demo",
      "manual_allowed": true,
      "automated_allowed": false,
      "human_review_required": true,
      "preconditions": ["adcs_passive_or_operator_approved", "wheel_and_torque_selected_by_operator"],
      "verifier": {"target": "GENERIC_REACTION_WHEEL", "packet": "GENRW_HK_TLM_T", "item": "MOMENTUM_NMS_selected_wheel", "condition": "changes"},
      "timeout_seconds": 30,
      "result_classification": "manual_attitude_effect"
    },
    {
      "id": "mgr_set_ak_enable",
      "status": "automation_allowed_with_review",
      "simulator_only": true,
      "target": "MGR_RADIO",
      "command": "MGR_SET_AK_CC",
      "args": [{"name": "AK_STATUS", "type": "UINT8_ENUM", "allowed_values": {"DISABLE": 0, "ENABLE": 1}, "value": "ENABLE"}],
      "intent": "enable_science_region_ak",
      "manual_allowed": true,
      "automated_allowed": true,
      "human_review_required": true,
      "preconditions": ["target_present:MGR_RADIO", "commissioning_or_science_config_context"],
      "verifier": {"target": "MGR_RADIO", "packet": "MGR_HK_TLM", "item": "AK_CONFIG", "condition": "equals:ENABLED"},
      "timeout_seconds": 15,
      "result_classification": "success_when_ak_enabled"
    },
    {
      "id": "eps_switch7_off_manual",
      "status": "manual_only",
      "simulator_only": true,
      "target": "GENERIC_EPS",
      "command": "GENERIC_EPS_SWITCH_CC",
      "args": [
        {"name": "SWITCH_NUMBER", "type": "UINT8_ENUM", "allowed_values": {"SWITCH_0": 0, "SWITCH_1": 1, "SWITCH_2": 2, "SWITCH_3": 3, "SWITCH_4": 4, "SWITCH_5": 5, "SWITCH_6": 6, "SWITCH_7": 7, "UNDEFINED": 255}, "value": "SWITCH_7"},
        {"name": "STATE", "type": "UINT8_ENUM", "allowed_values": {"OFF": 0, "ON": 170}, "value": "OFF"}
      ],
      "intent": "manual_low_power_switch7_off",
      "manual_allowed": true,
      "automated_allowed": false,
      "human_review_required": true,
      "preconditions": ["low_power_scenario_active", "switch7_verified_unexpectedly_on", "operator_confirms_switch7_nonessential"],
      "verifier": {"target": "GENERIC_EPS", "packet": "GENERIC_EPS_HK_TLM", "item": "SWITCH_7_STATE", "condition": "equals:OFF"},
      "timeout_seconds": 20,
      "result_classification": "manual_power_triage"
    },
    {
      "id": "eps_load_shed_policy",
      "status": "unresolved",
      "simulator_only": true,
      "target": null,
      "command": null,
      "args": [],
      "intent": "generic_eps_load_shed",
      "manual_allowed": false,
      "automated_allowed": false,
      "human_review_required": true,
      "preconditions": ["blocked_until_load_to_switch_policy_exists"],
      "verifier": null,
      "timeout_seconds": null,
      "result_classification": "blocked_unresolved_mapping"
    },
    {
      "id": "radiation_protect_generic",
      "status": "unresolved_rejected",
      "simulator_only": true,
      "target": null,
      "command": null,
      "args": [],
      "intent": "generic_radiation_protect",
      "manual_allowed": false,
      "automated_allowed": false,
      "human_review_required": true,
      "preconditions": ["blocked_no_nos3_target"],
      "verifier": null,
      "timeout_seconds": null,
      "result_classification": "blocked_no_nos3_target"
    }
  ]
}
```
