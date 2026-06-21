# CubeSat NOS3 Command Evidence

Generated: 2026-06-21

## Research Question

Can Soteria's simulated CubeSat be NOS3-backed on GCP, with commands based on an actual CubeSat-derived simulator command set rather than invented generic commands?

## Short Answer

Yes. The plan should be tightened from "NOS3-aligned lightweight simulator" to "NOS3-first simulator with a Soteria bridge." NOS3 is specifically documented as a software-only small-satellite/CubeSat simulator stack using cFS, dynamics/environment simulation, and ground software. Current NOS3 documentation shows COSMOS 5/OpenC3 support, cFS command/telemetry links, and concrete simulator commands that can seed the first Soteria command catalog. The important boundary is that these are actual NOS3/STF-style simulator commands, not real commands for an active spacecraft.

## Source-Backed Findings

| Source | What it shows | Plan implication |
| --- | --- | --- |
| [NOS3 Getting Started](https://nos3.readthedocs.io/en/latest/NOS3_Getting_Started.html) | NOS3 expects either Vagrant/VirtualBox or Linux with Docker and Docker Compose; standard flow is clone, submodules, `make prep`, `make`, `make launch`, and `make stop`. | GCP target should be a Linux Compute Engine VM that runs the actual NOS3 stack, not just a custom simulator. |
| [NOS3 Ground Systems](https://nos3.readthedocs.io/en/latest/NOS3_Ground_Software.html) | NOS3 supports COSMOS 5 via OpenC3, selects it with `gsw = openc3`, uses CI/TO apps for command/telemetry, and uses UDP links for NOS3 test communication. | Soteria should run OpenC3/COSMOS 5 as the ground system and keep the VM command path private. |
| [NOS3 Demonstration Scenario](https://nos3.readthedocs.io/en/latest/Scenario_Demo.html) | Shows concrete operator actions: `CFS CFE_ES_NOOP`, `TO_ENABLE_OUTPUT`, `CFS_RADIO`, `SAMPLE SAMPLE_NOOP_CC`, `SAMPLE_SIM_SET_STATUS`, `GENERIC_ADCS_SET_MODE_CC`, and `GENERIC_RW_SET_TORQUE_CC`. | The first command catalog can be made from documented NOS3 commands and telemetry verifiers. |
| [NOS3 Commissioning Scenario](https://nos3.readthedocs.io/en/latest/Scenario_Commissioning.html) | Shows COSMOS script commands for radio output, sample instrument enable/disable, EPS voltage telemetry, spacecraft mode telemetry, and science-region configuration. | Soteria command rows should store target, command, arguments, COSMOS script form, and verifier telemetry. |
| [NOS3 Low Power Scenario](https://nos3.readthedocs.io/en/latest/Scenario_Low_Power.html) | Uses a low-power spacecraft scenario, EPS switch telemetry, switch-off action, and command/script fault triage. | Power-load-shed behavior should be NOS3 scenario-backed; exact EPS switch command must be read from the NOS3 command dictionary before automation. |
| [NOS3 Simulators](https://nos3.readthedocs.io/en/latest/NOS3_Simulators.html) | NOS3 simulators use NOS Engine to simulate hardware buses such as UART, I2C, SPI, CAN, and discrete I/O; custom hardware models and data providers are XML-driven. | The compute payload should be a NOS3 component/hardware model, not an arbitrary external process pretending to be spacecraft state. |
| [NASA cFS repository](https://github.com/nasa/cFS) | cFS is a generic flight software framework used on flagship spacecraft, human spacecraft, CubeSats, and development boards; the public bundle includes example/lab apps and is not itself a flight distribution. | Use cFS/NOS3 as a simulator/testbed and mark outputs simulator-only. Do not imply flight qualification. |
| [NOS3 STF-1 CubeSat case study](https://arxiv.org/abs/1901.07583) | NOS3 was developed for the STF-1 3U CubeSat mission and combines hardware simulators, 42 dynamics, cFS, and COSMOS for software development, testing, training, and operations. | This is a credible CubeSat-derived simulator basis for Soteria. |
| [NOAA Space Weather Scales](https://www.swpc.noaa.gov/noaa-scales-explanation) | NOAA maps geomagnetic, solar radiation, and radio blackout scales to satellite effects including charging, drag, orientation, memory, imaging noise, star tracker, solar panel, radio, and navigation impacts. | Space-weather-to-command policies are physically motivated, but still require simulator-specific command gates and telemetry verification. |
| [Satellite drag analysis during May 2024 geomagnetic storm](https://arxiv.org/abs/2406.08617) | Recent LEO observations show geomagnetic storm density/drag impacts can be operationally meaningful and hard to forecast precisely. | The agent should be conservative about LEO drag/attitude recommendations and verify model assumptions against telemetry. |

## Source-Backed NOS3 Command Seed Catalog

These commands are eligible for the first Soteria simulator catalog because they are documented in NOS3 scenarios or NOS3 ground-system guidance. They are simulator commands only.

| Soteria intent | NOS3/OpenC3 command record | Arguments | Verifier telemetry or behavior | Evidence status |
| --- | --- | --- | --- | --- |
| Connectivity check | Target `CFS`, command `CFE_ES_NOOP` | none | `CFS` command counter increments and FSW console reports the command | Documented in NOS3 Demonstration Scenario |
| Enable radio telemetry | Target `CFS_RADIO`, command `TO_ENABLE_OUTPUT` | `DEST_IP = radio-sim`, `DEST_PORT = 5011` | `CFS_RADIO` telemetry starts and command/telemetry server activity increases | Documented in NOS3 Ground Systems and Commissioning Scenario |
| Resume radio telemetry | Target `CFS_RADIO`, command `TO_RESUME_OUTPUT` | none | `CFS_RADIO` packets become fresh | Documented in NOS3 Commissioning Scenario |
| Disable radio telemetry | Target `CFS_RADIO`, command `TO_DISABLE_OUTPUT` | none | Radio telemetry output stops | Documented in NOS3 Commissioning Scenario |
| Sample payload NOOP | Target `SAMPLE`, command `SAMPLE_NOOP_CC` | none | `SAMPLE_HK_TLM CMD_COUNT` increments | Documented in NOS3 Demonstration Scenario |
| Enable sample instrument | Target `SAMPLE_RADIO`, command `SAMPLE_ENABLE_CC` | none | `SAMPLE` telemetry becomes fresh; simulator communicates with app | Documented in NOS3 Commissioning Scenario |
| Disable sample instrument | Target `SAMPLE_RADIO`, command `SAMPLE_DISABLE_CC` | none | Sample payload telemetry/state indicates disabled/off | Documented in NOS3 Commissioning Scenario |
| Inject sample device fault | Target `SIM_CMD_BUS_BRIDGE`, command `SAMPLE_SIM_SET_STATUS` | `status = 5` in the scenario | Sample simulator receives changed status; FSW reports device disabled/status error | Documented in NOS3 Demonstration Scenario |
| Set ADCS passive | Target `GENERIC_ADCS`, command `GENERIC_ADCS_SET_MODE_CC` | `GNC_MODE = PASSIVE` or numeric `0` | 42 visual and ADCS telemetry show passive/tumbling behavior | Documented in NOS3 Demonstration Scenario |
| Set ADCS sun-safe | Target `GENERIC_ADCS`, command `GENERIC_ADCS_SET_MODE_CC` | `GNC_MODE = SUNSAFE_MODE` or numeric `2` | `GENERIC_ADCS MODE` and 42 visual show sun-safe pointing | Documented in NOS3 Demonstration Scenario |
| Reaction wheel torque demo | Target `GENERIC_REACTION_WHEEL`, command `GENERIC_RW_SET_TORQUE_CC` | torque arguments from NOS3 command dictionary | Spacecraft attitude changes in 42; wheel telemetry updates | Documented in NOS3 Demonstration Scenario |
| Enable science region AK | Target `MGR_RADIO`, command `MGR_SET_AK_CC` | `AK_STATUS = ENABLE` | `MGR MGR_HK_TLM` confirms science-region state | Documented in NOS3 Commissioning Scenario |
| EPS switch load shed | Exact target/command to be extracted from NOS3 command dictionary before automation | switch number and state | EPS switch telemetry shows switch off and current draw decreases | Low-power scenario documents the operational action; exact command must be dictionary-verified |

## Science Check

| Claim | Verdict | Evidence | Confidence |
| --- | --- | --- | --- |
| NOS3 is an appropriate CubeSat-derived simulator base for Soteria. | Supported | NOS3's STF-1 case study describes a software-only simulator developed for a 3U CubeSat and combining hardware simulators, 42, cFS, and COSMOS. NOS3 docs currently document stock scenarios and OpenC3/COSMOS 5 support. | High |
| Soteria can use actual simulator commands rather than invented commands. | Supported with boundary | NOS3 docs provide named commands and target/argument examples. The boundary is that these commands are actual NOS3 simulator commands, not universal spacecraft commands. | High |
| NOS3 can be deployed on a GCP Compute Engine VM. | Supported, but needs an ops spike | NOS3 docs support Linux with Docker and Docker Compose. GCE Linux VMs can run Docker, so this is technically straightforward, but OpenC3 GUI access, ports, persistent volumes, and VM sizing need validation. | Medium |
| Space-weather-triggered protective actions are physically motivated. | Supported | NOAA's scales explicitly tie geomagnetic storms, solar radiation storms, and radio blackouts to satellite operations impacts. Recent LEO drag analysis supports geomagnetic drag relevance. | High |
| NOS3 stock configuration fully models space-weather physics out of the box. | Not enough information / likely incomplete | NOS3 includes 42 dynamics/environment and simulated hardware. The inspected docs do not show stock modeling for all space-weather effects Soteria wants, such as radiation single-event effects, charging risk, or thermospheric density changes from forecasts. | Medium |
| The first Soteria implementation should auto-execute every agent-selected command. | Contradicted | NOS3 documentation warns the UDP command links are test/development paths, cFS public bundle is a starting point rather than flight-qualified, and command safety docs in Soteria require source-backed commands and review. | High |

## Mechanism And Constraints

- Mechanism: Soteria should treat Supabase as the product I/O bus, while the GCE VM runs NOS3 + OpenC3/COSMOS 5 as the actual simulator/ground-system layer. A Soteria NOS3 bridge translates approved command rows into OpenC3/NOS3 commands and writes telemetry/result rows back to Supabase.
- Command source: The first catalog should be extracted from NOS3 OpenC3 command definitions and scenario scripts, then stored as a versioned command dictionary in Soteria. Commands missing from that dictionary should be returned as unresolved.
- CubeSat realism: NOS3/STF-1 gives a real CubeSat-derived simulator baseline. Soteria can model a 6U edge-compute CubeSat by extending NOS3 with a compute-payload component, but the baseline command examples should remain clearly labeled as NOS3/STF simulator commands until the new component is implemented.
- Space-weather limits: NOAA scales justify protective command families, but stock NOS3 may need additional data providers/fault injectors for drag, radiation, charging, star-tracker degradation, GNSS/navigation uncertainty, and radio-link degradation.
- Safety: The bridge should never expose raw OpenC3 or UDP command links publicly. Commands should move through Supabase with idempotency, expiry, allowlist validation, and telemetry verification.

## What Would Make This Stronger

- Clone NOS3 at a pinned commit or release and extract the OpenC3 target command definitions directly from the repository.
- Run stock NOS3 on a Linux VM with `gsw = openc3`, send `CFE_ES_NOOP`, enable radio telemetry, enable/disable the sample instrument, set ADCS passive/sun-safe, and reproduce the low-power scenario.
- Build a small command dictionary from the actual OpenC3 target files and compare it against the table above.
- Measure GCE VM sizing for OpenC3 + cFS + simulators under steady telemetry.
- Add a custom NOS3 `compute_payload` component only after stock command/telemetry bridging is proven.

## What Would Falsify The Plan

- NOS3 cannot run reliably on the chosen GCE Linux VM profile.
- OpenC3 command automation cannot be safely scripted or integrated without bypassing command validation.
- The command dictionary cannot be extracted into stable target/command/argument/verifier records.
- Supabase command polling/realtime latency causes duplicate or stale command execution.
- Stock NOS3 telemetry cannot provide enough state to verify Soteria's agent actions without a custom component.

## Plan Changes Required

- Change the first release from a custom lightweight simulator to a NOS3-backed simulator service.
- Keep the lightweight synthetic state model only as an optional fallback for local tests, not as the production simulator core.
- Replace generic command names in the task plan with source-backed NOS3 command records.
- Add a mandatory task to extract and version the NOS3 command dictionary from OpenC3/COSMOS target definitions and scenario scripts.
- Add a mandatory science/engineering gap task for space-weather physics not modeled by stock NOS3.
