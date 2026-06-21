# CubeSat NOS3 OpenC3 Bench Runbook

Generated: 2026-06-21

This runbook defines the first reproducible bench for starting stock NOS3 with OpenC3/COSMOS 5 as the ground system and proving that OpenC3 sees fresh cFS/NOS3 telemetry. It is a planning and execution artifact; it does not claim that this agent launched NOS3.

## Source Basis

| Source | Bench-relevant fact |
| --- | --- |
| [NOS3 Getting Started](https://nos3.readthedocs.io/en/latest/NOS3_Getting_Started.html) | Linux installs use Git plus Docker and Docker Compose, then `make prep`, `make`, `make launch`, and `make stop`. |
| [NOS3 Ground Systems](https://nos3.readthedocs.io/en/latest/NOS3_Ground_Software.html) | COSMOS 5 is provided through OpenC3, selected by setting `gsw` in `cfg/nos3-mission.xml` to `openc3`; cFS CI/TO links use UDP and are for development/test, not flight operations. |
| [OpenC3 cFS guide](https://docs.openc3.com/docs/guides/cfs) | OpenC3 cFS integrations use a `CFS` target and UDP telecommand/telemetry ports; example cFS housekeeping includes command counters and telemetry time fields. |
| [OpenC3 Command Sender](https://docs.openc3.com/docs/tools/cmd-sender) | Command Sender uses target and packet dropdowns, populates command parameters, records command history, and preserves hazardous-command prompts. |
| [OpenC3 Telemetry Viewer](https://docs.openc3.com/docs/tools/tlm-viewer) | Telemetry Viewer selects screens by target and can generate packet-based screens for live telemetry inspection. |
| [OpenC3 installation](https://docs.openc3.com/docs/getting-started/installation) | OpenC3's documented local browser endpoint is `http://localhost:2900`; recommended Docker resources are 16 GB RAM, 2+ CPUs, and 100 GB disk. |
| [NOS3 GitHub releases](https://github.com/nasa/nos3/releases) and [tags](https://github.com/nasa/nos3/tags) | Latest verified release during this research pass was release 1.7.4, tag `v1_07_04`, short commit `4428de5`, dated 2026-01-19. |
| [GCE E2 machine types](https://docs.cloud.google.com/compute/docs/general-purpose-machines#e2_machine_types) | `e2-standard-4` provides 4 vCPU and 16 GB RAM; `e2-standard-8` provides 8 vCPU and 32 GB RAM. |
| [GCE Ubuntu OS details](https://docs.cloud.google.com/compute/docs/images/os-details) | Ubuntu 24.04 LTS is a supported Google-provided x86 image family. |
| [IAP TCP forwarding](https://docs.cloud.google.com/iap/docs/using-tcp-forwarding) | IAP ingress uses source range `35.235.240.0/20` and can forward TCP connections to VM ports. |
| [Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/) and [Compose plugin](https://docs.docker.com/compose/install/linux/) | Install Docker CE from Docker's apt repository with `docker-compose-plugin`; verify with `docker --version` and `docker compose version`. |

## Reuse Decision

Adopt the stock NOS3 Docker/Docker Compose flow first. Do not create a Soteria-specific container layout, custom OpenC3 deployment, or custom compute-payload component until this bench proves that stock NOS3 can start with `gsw = openc3` and that OpenC3 shows fresh telemetry from cFS/NOS3.

## Version Pin

Use the NOS3 release tag below for the bench:

```bash
NOS3_REPO=https://github.com/nasa/nos3.git
NOS3_TAG=v1_07_04
NOS3_RELEASE=1.7.4
NOS3_EXPECTED_SHORT_SHA=4428de5
```

Bench-time pinning procedure:

```bash
git clone "${NOS3_REPO}" ~/nos3-bench/nos3
cd ~/nos3-bench/nos3
git fetch --tags origin
git checkout "${NOS3_TAG}"
git submodule update --init --recursive
git describe --tags --exact-match
git rev-parse HEAD
```

Expected evidence:

```text
git describe --tags --exact-match -> v1_07_04
git rev-parse --short HEAD -> 4428de5
git rev-parse HEAD -> <record full bench-time SHA here>
```

The exact full SHA is a bench-time value because this task did not clone or run NOS3. Record it in the bench notes before building.

## Host Environment Target

Primary GCE bench profile:

| Item | Target |
| --- | --- |
| VM name | `soteria-nos3-bench` |
| Region/zone | `us-central1` / `us-central1-a`, unless the project standard differs |
| Machine type | `e2-standard-4` / 4 vCPU / 16 GB RAM |
| Expansion profile | `e2-standard-8` / 8 vCPU / 32 GB RAM if stock NOS3 fails on `e2-standard-4` |
| OS | Ubuntu 24.04 LTS x86_64 from `ubuntu-os-cloud` image family `ubuntu-2404-lts` |
| Boot disk | 200 GB balanced persistent disk |
| Docker | Docker CE from Docker's Ubuntu apt repo, with Compose v2 plugin available as `docker compose` |
| Git | NOS3 docs require Git 2.47+. Verify and upgrade before cloning if the base image is older. |
| External IP | Prefer none. Use Cloud NAT or a controlled egress path for apt/GitHub/Docker pulls. |
| Inbound firewall | TCP 22 from IAP source range `35.235.240.0/20` only |
| OpenC3 UI access | SSH/IAP local forward to `http://localhost:2900`; do not expose TCP 2900 publicly |
| Internal/private ports | OpenC3 HTTP `2900` on VM loopback or Docker host binding; cFS/OpenC3 UDP command/telemetry ports remain Docker/VM-private; NOS3 radio telemetry uses the documented `CFS_RADIO TO_ENABLE_OUTPUT` flow with `DEST_PORT=5011` internally |

Do not create firewall rules for OpenC3, cFS UDP, NOS3 simulator, or radio ports. The browser UI, command links, and UDP links remain private even for the bench.

## GCE Setup Commands

Run these from an operator workstation with `gcloud` configured. Replace the project, network, and subnet values before execution.

```bash
export PROJECT_ID="<gcp-project-id>"
export REGION="us-central1"
export ZONE="us-central1-a"
export NETWORK="default"
export SUBNET="default"
export VM_NAME="soteria-nos3-bench"
export VM_TAG="soteria-nos3-bench"

gcloud config set project "${PROJECT_ID}"
gcloud services enable compute.googleapis.com iap.googleapis.com
```

If the subnet has no existing private egress path, create Cloud NAT first:

```bash
gcloud compute routers create soteria-nos3-nat-router \
  --network="${NETWORK}" \
  --region="${REGION}"

gcloud compute routers nats create soteria-nos3-nat \
  --router=soteria-nos3-nat-router \
  --region="${REGION}" \
  --nat-all-subnet-ip-ranges \
  --auto-allocate-nat-external-ips
```

Create the VM without an external IP:

```bash
gcloud compute instances create "${VM_NAME}" \
  --zone="${ZONE}" \
  --machine-type=e2-standard-4 \
  --image-family=ubuntu-2404-lts \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=200GB \
  --boot-disk-type=pd-balanced \
  --network="${NETWORK}" \
  --subnet="${SUBNET}" \
  --no-address \
  --tags="${VM_TAG}"
```

Allow SSH only through IAP:

```bash
gcloud compute firewall-rules create allow-iap-ssh-soteria-nos3 \
  --network="${NETWORK}" \
  --direction=INGRESS \
  --action=ALLOW \
  --rules=tcp:22 \
  --source-ranges=35.235.240.0/20 \
  --target-tags="${VM_TAG}"
```

Connect through IAP:

```bash
gcloud compute ssh "${VM_NAME}" \
  --zone="${ZONE}" \
  --tunnel-through-iap
```

Expected evidence:

```text
hostname -> soteria-nos3-bench or the project-specific VM hostname
curl -s ifconfig.me -> succeeds only if a private egress path exists; not required for OpenC3 access
```

## VM Bootstrap

Run on the VM:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg git make python3 python3-pip python3-venv build-essential

sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker "${USER}"
```

Log out and reconnect, or run `newgrp docker` for the current shell, then verify:

```bash
git --version
docker --version
docker compose version
docker run --rm hello-world
```

Expected evidence:

```text
git version >= 2.47.x
Docker Engine is installed and the daemon is running
Docker Compose v2 is available through `docker compose`
hello-world prints Docker's success message
```

Expected deviation: Ubuntu 24.04 package repositories may provide Git below NOS3's documented 2.47+ prerequisite. If so, upgrade Git through an approved image/package path, record the command used, and rerun `git --version` before cloning NOS3.

## Clone And Configure NOS3

Run on the VM:

```bash
mkdir -p ~/nos3-bench
cd ~/nos3-bench
git clone https://github.com/nasa/nos3.git
cd nos3
git fetch --tags origin
git checkout v1_07_04
git submodule update --init --recursive
git describe --tags --exact-match
git rev-parse HEAD
```

Edit `cfg/nos3-mission.xml` and set the `gsw` parameter to `openc3`.

Verification command:

```bash
grep -n "gsw" cfg/nos3-mission.xml
```

Expected evidence:

```text
The `gsw` parameter in cfg/nos3-mission.xml is set to `openc3`.
The checked-out tag is `v1_07_04`.
The full commit SHA is recorded in the bench notes.
```

If NOS3 was previously built with another ground system on this VM, switch cleanly before rebuilding:

```bash
make stop-gsw
make clean
```

## Build And Start Stock NOS3

Run from `~/nos3-bench/nos3`:

```bash
make prep
make
make launch
```

Expected process evidence:

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -Ei "openc3|cosmos|cfs|nos3|42|radio|sim"
```

Expected result:

```text
At least one OpenC3/COSMOS 5 container is running.
At least one cFS/NOS3 flight software process or container is running.
NOS3 simulator/radio/42-related processes or containers are present according to the release's stock process shape.
No public firewall rule exposes TCP 2900 or cFS/NOS3 UDP ports.
```

If `make launch` fails on `e2-standard-4`, collect `docker ps -a`, failing container logs, `free -h`, and `df -h`, then test `e2-standard-8` before changing the architecture. Only fall back to local execution if the failure is clearly GCE-specific and documented.

## Private OpenC3 Access

From the operator workstation, create a private browser tunnel:

```bash
gcloud compute ssh "${VM_NAME}" \
  --zone="${ZONE}" \
  --tunnel-through-iap \
  -- -L 2900:localhost:2900
```

Open the UI locally:

```text
http://localhost:2900
```

Expected evidence:

```text
The OpenC3/COSMOS 5 browser UI loads through the local forwarded URL.
The captured access method is "IAP SSH local forward to http://localhost:2900".
No credentials, passwords, tokens, cookies, or screenshots containing credentials are committed to this doc.
```

If OpenC3 prompts for a first-run UI password or login setup, choose bench credentials in the operator's password manager. Do not record them in the repository.

## Telemetry Verification

Confirm the OpenC3 target list first:

1. Open OpenC3 through `http://localhost:2900`.
2. Open Command Sender and inspect the target dropdown.
3. Confirm target `CFS` is present.
4. Confirm at least one NOS3 subsystem target is present, such as `CFS_RADIO`, `SAMPLE`, `SAMPLE_RADIO`, `GENERIC_ADCS`, or another target provided by the checked-out NOS3 release.

Confirm fresh cFS telemetry:

1. Open Packet Viewer or Telemetry Viewer.
2. Select target `CFS`.
3. Select a housekeeping packet such as `HK` if available.
4. Confirm fields such as packet time, `CMD_CNT`, or `CMD_ERRS` are updating or have a recent receive timestamp.
5. Record the observed target, packet, item names, and timestamp in the bench notes.

If only the default debug telemetry is visible and radio telemetry is required for the bench, enable the documented radio TO link manually from Command Sender:

```text
Target: CFS_RADIO
Command: TO_ENABLE_OUTPUT
Arguments: DEST_IP = radio-sim, DEST_PORT = 5011
```

Expected evidence after radio enable:

```text
OpenC3 reports the command was sent.
The TO app reports telemetry enabled, or OpenC3 Command and Telemetry Server byte counters increase.
CFS/NOS3 packets become fresh in OpenC3.
Radio/cFS/simulator logs show frequent output.
```

This radio-enable command is only a bench connectivity step. Do not treat it as a complete command catalog or automated bridge validation.

## Stop And Restart

Stop the stack:

```bash
cd ~/nos3-bench/nos3
make stop
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Expected result:

```text
NOS3/OpenC3 containers from the stock stack are stopped, or only unrelated system containers remain.
```

Restart from a clean stopped state:

```bash
cd ~/nos3-bench/nos3
make launch
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -Ei "openc3|cosmos|cfs|nos3|42|radio|sim"
```

Repeat the private OpenC3 access and telemetry verification steps. Expected result: cFS/NOS3 telemetry becomes fresh again after restart.

## Bench Validation To Run

- [ ] VM matches the target profile: Ubuntu 24.04 LTS, `e2-standard-4`, 200 GB disk, no external IP, IAP SSH only.
- [ ] `git --version`, `docker --version`, and `docker compose version` are recorded.
- [ ] NOS3 tag is `v1_07_04`; full commit SHA is recorded; short SHA begins with `4428de5`.
- [ ] `cfg/nos3-mission.xml` has `gsw` set to `openc3`.
- [ ] `make prep`, `make`, and `make launch` complete without custom container layout changes.
- [ ] `docker ps` shows OpenC3/COSMOS 5, cFS/NOS3, and simulator/radio/42-related stock processes or containers.
- [ ] OpenC3 loads only through a private access method: IAP SSH local forward to `http://localhost:2900`.
- [ ] No firewall rule exposes TCP 2900, cFS UDP, NOS3 simulator, or radio ports publicly.
- [ ] OpenC3 target list contains `CFS`.
- [ ] OpenC3 target list contains at least one NOS3 subsystem target.
- [ ] OpenC3 shows fresh cFS/NOS3 telemetry before custom bridge design continues.
- [ ] Stack is stopped with `make stop`.
- [ ] Stack is restarted once from the clean stopped state with `make launch`.
- [ ] Telemetry becomes fresh again after restart.
- [ ] Access URL/method is captured without credentials.
- [ ] Every deviation from the public NOS3/OpenC3 docs is recorded.

## Evidence To Capture

Store evidence in bench notes or a private handoff artifact, not in this doc if it contains credentials or sensitive project details:

- `gcloud compute instances describe "${VM_NAME}" --zone="${ZONE}"` summary showing machine type, disk size, tags, no external NAT IP, and zone.
- `gcloud compute firewall-rules list --filter="targetTags:${VM_TAG}"` or equivalent showing only IAP SSH ingress.
- `git describe --tags --exact-match`, `git rev-parse HEAD`, and `git submodule status`.
- `git --version`, `docker --version`, `docker compose version`, `docker ps`.
- The exact `gsw` line or XML value from `cfg/nos3-mission.xml`.
- OpenC3 access method: `IAP SSH local forward to http://localhost:2900`.
- OpenC3 target list observation with `CFS` and at least one NOS3 subsystem target.
- Telemetry observation: target, packet, item names, receive/update timestamp before and after restart.
- Any setup deviations, failed commands, and the machine profile used for the retry if `e2-standard-8` is needed.

## Known Setup Deviations And Risks

- This runbook did not launch NOS3; all runtime evidence is to be collected during bench execution.
- NOS3 docs require Git 2.47+. Ubuntu 24.04's default Git may be older, so the bench may need a Git upgrade before cloning.
- Docker and Docker Compose exact versions are intentionally bench-time values because Docker apt repository versions change. Record them before `make prep`.
- NOS3 public docs are written around local VM/Linux desktop workflows. If `make prep` or `make launch` fails only because the GCE VM is headless or has no display/terminal launcher, record it as a GCE-specific display-path deviation before falling back to local; if the failure is CPU, memory, or disk pressure, test `e2-standard-8` first.
- The OpenC3 first-run password and any backend credentials must stay out of repository docs.
- NOS3 cFS CI/TO UDP links are development/test links and must stay private. They are not a production command path.
- If the stock flow fails, test one larger GCE machine profile before proposing a different architecture.
