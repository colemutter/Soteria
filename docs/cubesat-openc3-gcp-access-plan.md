# CubeSat OpenC3 GCP Access Plan

Generated: 2026-06-21

This plan is simulator-only. It describes how Soteria should protect access to
a NOS3-backed OpenC3/COSMOS 5 bench on Google Cloud. It is not a live resource
creation procedure, not a flight operations security plan, and not a claim of
spacecraft command authority.

## Decision

Recommended first slice: run NOS3, OpenC3, and the first Soteria OpenC3 bridge
on one Compute Engine VM in a restricted VPC subnet with no external IP address.
OpenC3 remains bound to loopback or Docker-private networking. Operators reach
the OpenC3 browser UI through IAP-secured SSH local forwarding to
`http://127.0.0.1:2900`. The bridge calls OpenC3 from the same VM at
`http://127.0.0.1:2900/openc3-api/api`.

Do not expose OpenC3 UI, JSON API, Script Runner, Redis, object storage, cFS UDP,
or NOS3 simulator links to the public internet. Supabase and OpenC3 credentials
must come from Secret Manager or VM-injected runtime secrets, not repository
files, Supabase command rows, frontend bundles, screenshots, or logs.

## Source Basis

| Source | Access-plan fact |
| --- | --- |
| [T1 bench runbook](./cubesat-nos3-openc3-bench-runbook.md) | The bench target is a GCE Ubuntu VM without an external IP, with OpenC3 accessed privately at `http://localhost:2900` and no public firewall rule for OpenC3 or simulator ports. |
| [T4 automation decision](./cubesat-openc3-automation-decision.md) | The bridge sends source-backed commands through the OpenC3 JSON API, writes `cubesat_command_results`, rejects direct cFS/UDP as production automation, and stores OpenC3 automation credentials outside committed config. |
| [Parent task plan](../agents/cubesat-nos3-openc3-commanding-subtasks.md) | OpenC3 UI/API must not be public; operators use IAP, VPN, or tunnel access; the bridge runs on the same VM or private network as OpenC3. |
| [OpenC3 installation](https://docs.openc3.com/docs/getting-started/installation) | OpenC3 connects in a browser at `http://localhost:2900`; production deployments should change default passwords. |
| [OpenC3 JSON API](https://docs.openc3.com/docs/development/json-api) | External apps can send commands and read telemetry through JSON-RPC at `/openc3-api/api` on port `2900`; requests require an `Authorization` token. |
| [OpenC3 security](https://docs.openc3.com/docs/getting-started/security) | COSMOS defaults to localhost listening, discourages direct public internet exposure, separates frontend and backend credentials, recommends changing defaults, limiting host access, firewalling access, and protecting `.env`/ACL files. |
| [OpenC3 architecture](https://docs.openc3.com/docs/getting-started/architecture) | Browser/API traffic is routed through Traefik; Redis, worker services, buckets, and other internals should stay inside the Docker network. |
| [GCP IAP TCP forwarding](https://cloud.google.com/iap/docs/using-tcp-forwarding) | IAP can tunnel SSH and other TCP traffic to VMs without external IPs; firewall ingress must allow IAP source range `35.235.240.0/20` only to the intended ports; IAP access is controlled by IAM. |
| [GCP secure VM connections](https://cloud.google.com/solutions/connecting-securely) | VMs without external IPs can be reached through other VMs, IAP TCP forwarding, Cloud SDK, VPN, or bastions; SSH port forwarding is a documented secure access pattern. |
| [GCP VPC firewall rules](https://cloud.google.com/vpc/docs/firewalls) | Ingress sources and targets can be constrained by IP ranges, network tags, or service accounts; service accounts give stricter targeting than editable network tags. |
| [GCP Secret Manager IAM](https://cloud.google.com/secret-manager/docs/access-control) | Grant Secret Manager access to the bridge service account only for the exact required secrets. |
| [Cloud Audit Logs](https://cloud.google.com/logging/docs/audit) | Audit logs answer who did what, where, and when; Admin Activity is always written, while Data Access logs must be enabled for services where read access must be audited. |
| [IAP audit logging](https://cloud.google.com/iap/docs/audit-log-howto) | IAP audit logs expose principal email, caller IP, requested resource, and whether access was granted. |
| [Ops Agent](https://cloud.google.com/stackdriver/docs/solutions/agents/ops-agent) | The Ops Agent can collect VM system, journald, file-based, and structured application logs into Cloud Logging. |
| [Private services access](https://cloud.google.com/vpc/docs/private-services-access) | Private services access connects a consumer VPC to service-producer VPC-hosted managed services; it is not the first-slice operator path to a single OpenC3 VM. |

## Topology

```text
Operator workstation
  |
  | gcloud compute ssh --tunnel-through-iap -- -NL 2900:127.0.0.1:2900
  v
IAP TCP forwarding
  |
  | firewall allows tcp:22 only from 35.235.240.0/20
  v
GCE VM: soteria-nos3-bench, no external IP
  |
  | localhost / Docker-private
  +-- OpenC3 UI/API on 127.0.0.1:2900
  +-- Soteria OpenC3 bridge -> http://127.0.0.1:2900/openc3-api/api
  +-- NOS3, cFS, simulator, and OpenC3 UDP links inside Docker/VM-private networks
  |
  | HTTPS egress only, through approved private egress/NAT path
  v
Secret Manager, Cloud Logging, Supabase, package registries during bootstrap
```

First-slice rationale:

- IAP-secured SSH forwarding keeps OpenC3 bound to loopback, so no GCP firewall
  rule needs to expose TCP `2900`.
- A same-VM bridge avoids a new internal service-to-service firewall surface.
- A manual operator can still reach OpenC3 when bridge automation is disabled.
- VPN, bastion, direct IAP to port `2900`, and split bridge VM designs remain
  expansion paths after the single-VM bench is validated.

## Access Pattern Comparison

| Pattern | Fit for first slice | Decision |
| --- | --- | --- |
| IAP-secured SSH local forwarding | Strong. Works with a VM that has no external IP and lets OpenC3 listen only on loopback. IAM and IAP audit logs identify the operator. | Adopt. |
| Direct IAP TCP tunnel to OpenC3 port `2900` | Acceptable later, but requires OpenC3 to listen on the VM private IP and a firewall rule from IAP to `2900`. | Defer until operators need non-SSH browser forwarding. |
| Cloud VPN | Strong for a mature private operations network, but heavier than one protected bench VM. | Defer. |
| Bastion host | Useful where IAP is unavailable, but adds another exposed host to harden and audit. | Defer. |
| Plain public SSH tunnel | Avoid for first slice because it normally requires public SSH reachability. | Reject by default. |
| Private services access | Useful for supported producer/managed services such as Cloud SQL-style private endpoints, not direct operator access to this VM. | Not applicable for first slice. |

## Network And Firewall Plan

Use a dedicated subnet such as `soteria-sim-private-us-central1`. The VM should
have no external IPv4 or IPv6 address. If outbound internet is required for
package pulls, Docker images, or GitHub during bootstrap, use a controlled Cloud
NAT or equivalent egress path and remove or tighten that path after the bench is
stable.

Prefer firewall targets by VM service account, for example
`soteria-nos3-vm@PROJECT_ID.iam.gserviceaccount.com`, because service-account
targeting is harder to mutate accidentally than network tags. Network tags are
acceptable only for the bench if the project has not yet standardized service
account firewall targeting.

The default implied ingress deny is sufficient if no broad allow rules target
the VM. If adding an explicit deny-all guardrail, give the IAP allow rule a
higher precedence, meaning a lower numeric priority.

| Rule name | Direction | Priority | Target | Peer | Protocol/ports | Action | Purpose |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `allow-iap-ssh-soteria-nos3` | Ingress | `1000` | NOS3/OpenC3 VM service account or tag | source `35.235.240.0/20` | `tcp:22` | allow | Operator/admin SSH through IAP and SSH local forwarding. |
| Optional `deny-public-ingress-soteria-nos3` | Ingress | `2000` or lower precedence | NOS3/OpenC3 VM subnet or service account | source `0.0.0.0/0`, `::/0` | all | deny | Explicit guardrail documenting that public ingress is not part of the design. |
| No OpenC3 public rule | Ingress | n/a | none | none | `tcp:2900`, `tcp:7777`, OpenC3 internal ports | no rule | OpenC3 UI/API stays loopback or Docker-private; JSON API is not internet reachable. |
| No NOS3 simulator ingress rule | Ingress | n/a | none | none | cFS/OpenC3 UDP and NOS3 simulator ports | no rule | UDP command/telemetry and simulator links stay inside Docker/VM-private networking. |
| Optional future `allow-bridge-openc3-private` | Ingress | `1000` | OpenC3 VM service account | source bridge VM service account only | `tcp:2900` | allow | Only if the bridge moves to a separate private VM and OpenC3 binds a private interface. |
| Optional restricted egress | Egress | after dependency review | NOS3/OpenC3 VM service account | destinations: Secret Manager, Logging, Supabase, package registries | `tcp:443`, bootstrap-specific ports | allow | Use only after exact dependencies are known; log and review denied egress during hardening. |

Hard requirements:

- Delete or disable broad default ingress rules such as `default-allow-ssh` from
  `0.0.0.0/0` for this VM or subnet.
- Do not create firewall rules for `tcp:2900` from the internet, even with
  OpenC3 authentication enabled.
- Do not expose Redis, VersityGW/S3-compatible storage, OpenC3 worker services,
  cFS UDP, NOS3 radio, simulator, or 42 dynamics ports outside the VM/Docker
  network in the first slice.
- Enable firewall rule logging for the IAP SSH allow rule and any future
  bridge-to-OpenC3 private rule.

## Operator Access

Operator path:

```bash
gcloud compute ssh soteria-nos3-bench \
  --zone=us-central1-a \
  --tunnel-through-iap \
  -- -NL 2900:127.0.0.1:2900
```

The operator then opens `http://127.0.0.1:2900` locally. OpenC3 should still
require its frontend password. In COSMOS Core, the first frontend password is a
shared frontend credential, so GCP IAM/IAP/OS Login identity is the operator
identity of record for access to the VM. If later using COSMOS Enterprise,
Keycloak-backed user identity should be added to the audit trail.

Operator IAM:

| Principal | Minimum access | Notes |
| --- | --- | --- |
| `group:soteria-openc3-operators@example.com` | `roles/iap.tunnelResourceAccessor` scoped to the VM, with IAM condition `destination.port == 22`; OS Login role such as `roles/compute.osLogin`; minimal Compute read permissions needed by `gcloud compute ssh`. | No Secret Manager access and no broad Compute Admin. |
| `group:soteria-openc3-admins@example.com` | Break-glass admin roles for VM maintenance, firewall/IAM changes, and incident response. | Separate from normal operators; require MFA and periodic review. |
| Bridge VM service account | No operator login rights. | Used only by bridge and runtime secret/log access. |

Operator workstation requirements:

- Use user-managed Google identities with MFA.
- Use `gcloud` authenticated as the operator, not a shared account.
- Do not copy OpenC3 session tokens from browser dev tools into tickets, docs,
  chat, or command result rows.

## Service Account IAM

Use a user-managed VM service account instead of the Compute Engine default
service account. Do not grant project Owner, Editor, Compute Admin, or Secret
Manager Admin to the bridge/VM runtime identity.

| Runtime identity | Required access | Denied by default |
| --- | --- | --- |
| `soteria-nos3-vm@PROJECT_ID.iam.gserviceaccount.com` | `roles/logging.logWriter`; optional monitoring metric writer; Secret Manager accessor only on exact OpenC3/Supabase runtime secrets needed by the VM. | Project-wide Secret Manager access, broad Compute permissions, IAM mutation, public IP or firewall mutation permissions. |
| Future `soteria-openc3-bridge@PROJECT_ID.iam.gserviceaccount.com` | Same as above, plus source identity for the private `tcp:2900` firewall rule if the bridge moves off the OpenC3 VM. | Operator login, OpenC3 host admin rights, ability to edit its own IAM or firewall reachability. |
| Human operators | IAP tunnel and OS Login only. | Secret Manager access to bridge secrets and Supabase service keys. |

## Bridge Access

First-slice bridge path:

```text
Bridge process on same VM
  -> http://127.0.0.1:2900/openc3-api/api
  -> Authorization: <OpenC3 session token>
  -> JSON-RPC method `cmd`, `tlm`, `tlm_raw`, or `tlm_formatted`
```

Bridge controls:

- The bridge accepts catalog command IDs and typed allowlisted arguments from
  Supabase, never arbitrary target/command text from the frontend.
- The bridge writes a durable send-intent/result row before an OpenC3 command
  call, then writes the OpenC3 response/error and telemetry verifier result.
- The bridge must not call OpenC3 no-check command variants by default.
- The bridge must not expose its own raw command HTTP endpoint publicly.
- If the bridge moves to a separate VM, OpenC3 may bind to a private interface
  and firewall `tcp:2900` may be allowed only from the bridge service account.

## Secrets Plan

Store these as Secret Manager secrets or VM-injected runtime secrets. Secret
names below are placeholders, not required resource names.

| Secret | Used by | Storage/access rule |
| --- | --- | --- |
| `soteria-openc3-frontend-password` | Human operators | Password manager or break-glass Secret Manager access; not readable by bridge unless required for API auth in the bench. |
| `soteria-openc3-automation-password-or-token` | Bridge | Secret Manager; bridge service account can access only the current version. Token cached in process memory only. |
| `soteria-openc3-service-password` | OpenC3 backend services if deployment requires it | Runtime environment or root-readable file with `0600`; never committed `.env`. Change all defaults before deployment. |
| `soteria-openc3-redis-passwords` | OpenC3 containers | Runtime-injected `.env`/ACL material with restricted file permissions; consider hashed Redis ACL passwords where supported. |
| `soteria-openc3-bucket-passwords` | OpenC3 object/log storage containers | Runtime-injected only; rotate with OpenC3 rebuilds. |
| `soteria-supabase-service-key` | Bridge | Secret Manager; never exposed to frontend; grant bridge-only access. |
| `soteria-supabase-url` | Bridge | Runtime config. Treat as non-secret but keep with bridge config for consistency. |
| Optional `soteria-openc3-cli-offline-token` | Diagnostic CLI fallback | Absent or disabled by default; separate rotation and access from normal bridge auth. |

Runtime handling:

- Do not commit `.env`, generated secret files, OpenC3 session tokens, Supabase
  service keys, or operator passwords.
- If a file must exist on the VM, write it under an operations-owned directory,
  set owner to the service user, and use `chmod 600`.
- Enable Secret Manager Data Access audit logs for secret reads.
- Rotate OpenC3 and Supabase bridge credentials after staff changes, suspected
  exposure, bench rebuilds, failed audits, and on the project rotation cadence.
- Redact tokens, passwords, Authorization headers, Supabase keys, and OpenC3
  browser local storage values from application logs.

## Logs And Audit Trails

Required audit surfaces:

| Event | System of record | Required fields |
| --- | --- | --- |
| Operator starts IAP tunnel or SSH session | IAP audit logs, OS Login audit logs, VM auth logs collected by Ops Agent | Principal email, caller IP, VM resource, destination port, granted/denied result, timestamp. |
| Operator signs into OpenC3 UI | OpenC3 application logs where available; IAP/OS Login remains identity of record for COSMOS Core shared password | Timestamp, VM, source tunnel session, OpenC3 login success/failure if available. |
| Bridge reads a secret | Secret Manager Data Access logs | Bridge service account, secret name/version, timestamp, granted/denied result. |
| Bridge claims a command row | Bridge structured log and Supabase command row | `command_row_id`, `execution_id`, requester, catalog version, command ID, claim timestamp. |
| Bridge sends OpenC3 command | Bridge structured log, OpenC3 command history/logs, `cubesat_command_results` | `execution_id`, OpenC3 target/command/args, JSON-RPC id, timestamp, redacted auth context. |
| Bridge verifies telemetry | Bridge structured log and `cubesat_command_results` | Before/after packet/item/value, verifier timeout, result class. |
| Firewall, IAM, VM, or IAP policy changes | Cloud Audit Logs Admin Activity | Actor, changed resource, old/new policy or rule pointer, timestamp. |

Bridge log entries should be structured JSON and should include a trace or
correlation ID that also appears in `cubesat_command_results`. Logs must not
include command authority secrets. OpenC3 packet logs and command history are
supporting evidence, while Supabase result rows are the Soteria durable command
audit trail.

Suggested Cloud Logging views/queries:

- IAP/SSH access: `protoPayload.serviceName="iap.googleapis.com"` plus VM
  resource filters; OS Login and VM auth logs for shell login outcomes.
- Secret reads: `protoPayload.serviceName="secretmanager.googleapis.com"` and
  secret resource names for OpenC3/Supabase bridge secrets.
- Bridge command sends: application log name such as
  `soteria-openc3-bridge` with `jsonPayload.execution_id`.
- Firewall changes: Admin Activity logs for `compute.firewalls.*` methods.

## Emergency Disable Checklist

Use the narrowest disable that contains the incident.

1. Disable automation while preserving manual OpenC3 access:
   - Stop the bridge service/container or set a runtime flag such as
     `SOTERIA_BRIDGE_COMMANDING_ENABLED=false`.
   - Revoke the bridge service account's Secret Manager access to OpenC3 and
     Supabase bridge secrets if credential misuse is suspected.
   - Rotate the OpenC3 automation credential and Supabase service key before
     re-enabling.
   - Leave OpenC3 and the VM running so an operator can still connect through
     IAP and inspect Command Sender, Packet Viewer, and logs.
2. Disable operator access:
   - Remove the operator group from the VM-scoped IAP tunnel IAM binding, or
     disable the `allow-iap-ssh-soteria-nos3` firewall rule.
   - Keep a separate break-glass admin path under incident commander control.
3. Disable all OpenC3 command authority:
   - Stop the OpenC3/NOS3 stack or stop the VM.
   - Snapshot/preserve relevant logs before cleanup when practical.
   - Rotate OpenC3 frontend/backend credentials before restart.
4. Quarantine suspicious queued commands:
   - Pause the bridge worker.
   - Mark queued/running command rows as paused, expired, failed, or
     manual-review-required according to the T5 bridge contract.
   - Do not retry ambiguous sends until telemetry verification or human review
     determines the actual simulator state.
5. Verify containment:
   - Confirm there is still no external IP on the VM.
   - Confirm no firewall rule allows `tcp:2900`, OpenC3 internals, or simulator
     UDP ports from `0.0.0.0/0`.
   - Confirm bridge secrets have no active access path from frontend code.

## Validation Review

Unauthenticated internet client perspective:

- The VM has no external IP address.
- There is no public forwarding rule, public load balancer, or firewall rule for
  OpenC3 `tcp:2900`, JSON API, Script Runner, Redis, object storage, cFS UDP, or
  NOS3 simulator links.
- The only first-slice ingress is `tcp:22` from IAP source range
  `35.235.240.0/20`, and IAP requires IAM before traffic is forwarded.
- A scan from the internet should find no OpenC3 command surface.

Compromised frontend client perspective:

- The frontend can only submit catalog command requests through Supabase
  controls; it does not receive OpenC3 URL reachability, OpenC3 tokens, Supabase
  service keys, bridge credentials, or VM credentials.
- The bridge alone reads command rows, resolves catalog IDs, calls OpenC3, and
  writes `cubesat_command_results`.
- Even with a stolen browser bundle or Supabase anon key, the attacker cannot
  connect to `127.0.0.1:2900` on the VM and cannot read Secret Manager bridge
  secrets.

Manual operator while bridge disabled:

- Stop or disable the bridge service only.
- Confirm the operator can still run the IAP SSH local forward and load
  `http://127.0.0.1:2900`.
- Confirm Command Sender and telemetry tools still operate manually if OpenC3
  and NOS3 remain healthy.

## Integration Notes

- T5 should make `cubesat_command_results` the durable Soteria audit record and
  include Cloud Logging pointers for each bridge execution.
- T8 should verify end-to-end that an agent request cannot bypass Supabase row
  policy, the command catalog, the bridge, OpenC3 checks, or result recording.
- Terraform should be added only after this manual access model is validated.
- A future split-VM or managed instance group deployment must re-run this access
  review because it introduces a private `tcp:2900` bridge-to-OpenC3 firewall
  surface.

## Handoff Checklist

- Access model: same-VM bridge plus IAP-secured SSH local forwarding to private
  OpenC3.
- Firewall sketch: no public OpenC3/API/simulator ingress; IAP `tcp:22` only;
  optional future bridge-only private `tcp:2900`.
- Credential list: OpenC3 frontend, OpenC3 automation, OpenC3 backend service,
  Redis, bucket/object storage, Supabase service key, optional CLI token.
- Emergency controls: bridge disable, operator disable, all-command disable,
  command queue quarantine, credential rotation, firewall verification.
