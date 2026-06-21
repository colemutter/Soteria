# Real-Time NOAA Space Weather ETL With Airflow And Astronomer

This guide explains how to use Apache Airflow on Astronomer to ingest and ETL
NOAA SWPC product data in near real time.

Airflow is a workflow orchestrator, not a low-latency streaming system. For this
project, "real time" should mean reliable minute-level polling, idempotent
processing, observable failures, and fast downstream updates. If the product
needs sub-second delivery or unbounded event streams, put Kafka, Redpanda,
Pub/Sub, Kinesis, Flink, or Spark Streaming in front of the warehouse and let
Airflow orchestrate batch validation, backfills, and derived products.

## Target Outcome

Build an Astronomer-hosted Airflow deployment that:

- Polls selected SWPC endpoints every minute.
- Uses HTTP caching metadata to skip unchanged payloads.
- Stores immutable raw JSON for replay.
- Normalizes records into typed tables.
- Computes derived fields and NOAA G/R/S classifications.
- Publishes fresh app-ready tables or files.
- Alerts when ingestion is stale, schemas drift, or NOAA scale states change.

Use the NOAA endpoint details in
[NOAA SWPC Space Weather Products API Guide](./noaa-space-weather-api.md) as the
source of endpoint and classification semantics.

## Architecture

```text
NOAA SWPC /products and /json
        |
        v
Airflow DAG on Astronomer
        |
        +-- fetch endpoint manifests and HTTP headers
        +-- fetch changed JSON payloads
        +-- write raw payloads to object storage
        +-- normalize records into staging tables
        +-- classify G/R/S and derive features
        +-- publish app-ready tables, files, or API cache
        |
        v
Warehouse / object storage / app database
```

Recommended storage layers:

| Layer | Purpose | Example |
| --- | --- | --- |
| Raw | Exact NOAA payloads and response metadata | S3/GCS/Azure Blob path partitioned by endpoint and fetch time |
| Staging | Parsed endpoint-specific rows | Postgres, DuckDB, BigQuery, Snowflake, or Parquet |
| Curated | Deduplicated, typed observations | `swpc_kp`, `swpc_xray_flux`, `swpc_proton_flux`, `swpc_solar_wind_mag` |
| Serving | App-ready state and transitions | `current_noaa_scales`, `space_weather_alert_events` |

## Why Astronomer

Astronomer gives you a managed Airflow runtime, deployment packaging, local
development with the Astro CLI, secrets/connections management, scheduler and
worker operations, logs, metrics, and CI/CD hooks. Keep the repo shaped like a
standard Astro project:

```text
.
+-- dags/
|   +-- swpc_realtime_etl.py
+-- include/
|   +-- swpc/
|       +-- endpoints.py
|       +-- fetch.py
|       +-- normalize.py
|       +-- classify.py
+-- tests/
|   +-- test_swpc_realtime_etl.py
+-- airflow_settings.yaml
+-- Dockerfile
+-- packages.txt
+-- requirements.txt
```

Local commands:

```bash
astro dev init
astro dev start
astro dev restart
astro dev stop
astro deploy
```

Use `airflow_settings.yaml` only for local development connections, variables,
and pools. In deployed Astronomer environments, configure secrets and
environment variables through Astronomer deployment settings or your secret
backend.

## DAG Design

Run one small DAG frequently instead of one huge DAG that tries to do
everything. A one-minute schedule is reasonable because SWPC product responses
advertise minute-scale cache headers.

Important DAG settings:

```python
@dag(
    dag_id="swpc_realtime_etl",
    schedule="* * * * *",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=datetime.timedelta(seconds=55),
    default_args={
        "retries": 2,
        "retry_delay": datetime.timedelta(seconds=10),
    },
    tags=["swpc", "space-weather", "near-real-time"],
)
```

Why these choices:

- `schedule="* * * * *"` gives minute-level polling.
- `catchup=False` prevents a backlog of old polling runs after downtime.
- `max_active_runs=1` avoids overlapping writes for the same endpoint.
- Short retries handle transient NOAA/network failures without hiding longer
  outages.
- A timeout shorter than the interval keeps the DAG from piling up.

Avoid passing large JSON payloads through XCom. XCom is for small control values
such as object-storage paths, row counts, ETags, timestamps, and classifications.
Store payloads in object storage or a database and pass references between
tasks.

## Endpoint Set

Start with a compact endpoint list:

```python
SWPC_ENDPOINTS = [
    "/products/noaa-scales.json",
    "/products/alerts.json",
    "/products/noaa-planetary-k-index.json",
    "/products/noaa-planetary-k-index-forecast.json",
    "/products/summary/solar-wind-mag-field.json",
    "/products/summary/solar-wind-speed.json",
    "/json/goes/primary/xrays-6-hour.json",
    "/json/goes/primary/integral-protons-6-hour.json",
    "/json/ovation_aurora_latest.json",
    "/json/solar_regions.json",
]
```

Add secondary GOES and raw RTSW feeds when you need redundancy or deeper
explanatory features:

```python
EXTRA_ENDPOINTS = [
    "/json/goes/secondary/xrays-6-hour.json",
    "/json/goes/secondary/integral-protons-6-hour.json",
    "/json/rtsw/rtsw_mag_1m.json",
    "/json/rtsw/rtsw_wind_1m.json",
    "/json/planetary_k_index_1m.json",
]
```

## Task Layout

Use the TaskFlow API for the core ETL:

```text
load_endpoint_config
        |
        v
fetch_endpoint.expand(endpoint=endpoints)
        |
        v
normalize_payload.expand(fetch_result=fetch_results)
        |
        v
publish_current_state
        |
        v
emit_scale_transition_alerts
```

Dynamic task mapping is useful because each endpoint can be fetched and parsed
independently while keeping one DAG definition.

## Example DAG Skeleton

This is intentionally a skeleton. Put reusable logic in `include/swpc/` so the
DAG file stays readable and unit-testable.

```python
from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass

import pendulum
from airflow.decorators import dag, task
from airflow.models import Variable

SWPC_ORIGIN = "https://services.swpc.noaa.gov"


@dataclass
class Endpoint:
    path: str
    family: str
    cadence_seconds: int = 60


@dataclass
class FetchResult:
    endpoint: str
    changed: bool
    fetched_at: str
    raw_uri: str | None
    etag: str | None
    last_modified: str | None


@dag(
    dag_id="swpc_realtime_etl",
    schedule="* * * * *",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=dt.timedelta(seconds=55),
    default_args={"retries": 2, "retry_delay": dt.timedelta(seconds=10)},
    tags=["swpc", "space-weather", "near-real-time"],
)
def swpc_realtime_etl():
    @task
    def load_endpoint_config() -> list[dict]:
        endpoints = [
            Endpoint("/products/noaa-scales.json", "scales"),
            Endpoint("/products/alerts.json", "alerts"),
            Endpoint("/products/noaa-planetary-k-index.json", "kp"),
            Endpoint("/products/summary/solar-wind-mag-field.json", "solar_wind"),
            Endpoint("/products/summary/solar-wind-speed.json", "solar_wind"),
            Endpoint("/json/goes/primary/xrays-6-hour.json", "xray"),
            Endpoint("/json/goes/primary/integral-protons-6-hour.json", "protons"),
        ]
        return [asdict(endpoint) for endpoint in endpoints]

    @task(max_active_tis_per_dag=4)
    def fetch_endpoint(endpoint: dict) -> dict:
        # Implement in include/swpc/fetch.py:
        # - read previous ETag and Last-Modified for this endpoint
        # - GET with If-None-Match / If-Modified-Since
        # - on 304, return changed=False
        # - on 200, write raw payload and metadata to object storage
        # - update endpoint fetch state transactionally
        result = FetchResult(
            endpoint=endpoint["path"],
            changed=True,
            fetched_at=pendulum.now("UTC").to_iso8601_string(),
            raw_uri="s3://bucket/swpc/raw/example.json",
            etag=None,
            last_modified=None,
        )
        return asdict(result)

    @task
    def normalize_payload(fetch_result: dict) -> dict:
        if not fetch_result["changed"]:
            return {"endpoint": fetch_result["endpoint"], "rows": 0, "changed": False}

        # Implement in include/swpc/normalize.py:
        # - load raw JSON by URI
        # - detect object vs record array vs header-row array
        # - normalize endpoint-specific records
        # - upsert rows by natural key
        return {"endpoint": fetch_result["endpoint"], "rows": 1, "changed": True}

    @task
    def publish_current_state(results: list[dict]) -> dict:
        # Implement in include/swpc/classify.py and serving writer:
        # - compute current G/R/S state
        # - update current state table
        # - compute fresh/stale endpoint health
        return {"updated_endpoints": [r["endpoint"] for r in results if r["changed"]]}

    @task
    def emit_scale_transition_alerts(current_state: dict) -> None:
        # Emit Slack, PagerDuty, email, or app notifications only for transitions.
        print(current_state)

    endpoints = load_endpoint_config()
    fetch_results = fetch_endpoint.expand(endpoint=endpoints)
    normalized = normalize_payload.expand(fetch_result=fetch_results)
    current_state = publish_current_state(normalized)
    emit_scale_transition_alerts(current_state)


swpc_realtime_etl()
```

## HTTP Fetching Rules

Implement fetches with these rules:

- Use `If-None-Match` when you have an ETag.
- Use `If-Modified-Since` when you have a Last-Modified timestamp.
- Treat `304 Not Modified` as success with no downstream parse work.
- Store `status_code`, `etag`, `last_modified`, `content_length`,
  `content_type`, `fetched_at`, `source_timestamp`, and `raw_uri`.
- Enforce per-endpoint timeouts.
- Use a DAG-local task limit such as `max_active_tis_per_dag=4` to cap
  concurrent NOAA requests without requiring deployment-specific pool setup.
- Do not retry forever. After a few failures, mark endpoint health as stale and
  alert.

State table example:

```sql
create table swpc_endpoint_state (
  endpoint text primary key,
  etag text,
  last_modified text,
  last_success_at timestamptz,
  last_changed_at timestamptz,
  last_raw_uri text,
  last_status_code integer,
  consecutive_failures integer not null default 0
);
```

## Normalization Rules

Each endpoint needs a parser contract:

| Endpoint type | Parse strategy |
| --- | --- |
| Array of objects | Validate keys, parse `time_tag`, upsert by endpoint-specific natural key |
| Object keyed by offset/date | Flatten each key into a row with `offset_key` and nested scale fields |
| Header-row array | Treat row 0 as column names and remaining rows as records |
| Coordinate grid | Store raw grid plus derived tiles or summaries needed by the app |
| Message array | Store the raw message, parsed product ID, issue time, and extracted scale/event fields if present |

Natural keys should include the endpoint and enough dimensions to avoid
collisions:

- Kp: `endpoint`, `time_tag`
- GOES X-ray: `endpoint`, `time_tag`, `satellite`, `energy`
- GOES protons: `endpoint`, `time_tag`, `satellite`, `energy`
- Alerts: `product_id`, `issue_datetime`, hash of `message`
- NOAA scales: `date_stamp`, `time_stamp`, `offset_key`

## Transform And Classify

Curated transforms should:

- Normalize all timestamps to UTC.
- Preserve source endpoint, satellite, `active`, and quality flags.
- Deduplicate by natural key.
- Compute current G/R/S state from `/products/noaa-scales.json`.
- Compute derived G/R/S from raw Kp, proton, and X-ray feeds when available.
- Store both official and derived classifications with labels.
- Track scale transitions separately from raw level snapshots.

Serving table sketch:

```sql
create table swpc_current_state (
  key text primary key,
  observed_at timestamptz not null,
  source text not null,
  value_json jsonb not null,
  updated_at timestamptz not null default now()
);

create table swpc_scale_events (
  id bigserial primary key,
  scale_type text not null,
  previous_scale text,
  current_scale text,
  source text not null,
  observed_at timestamptz not null,
  emitted_at timestamptz not null default now(),
  evidence_json jsonb not null
);
```

## Airflow Connections, Variables, And Secrets

Use Airflow Connections for external systems:

- `swpc_http`: optional HTTP connection for `https://services.swpc.noaa.gov`.
- `raw_object_store`: S3/GCS/Azure credentials or an object-store connection.
- `warehouse`: database or warehouse destination.
- `alert_sink`: Slack, PagerDuty, email, or webhook destination.

Use Airflow Variables only for small non-secret configuration:

- endpoint lists or endpoint group names
- stale thresholds
- feature flags
- deployment environment name

Do not put secrets in DAG code, Variables, or committed local files. In
Astronomer, use deployment environment variables, configured Airflow
Connections, or a secrets backend.

## Astronomer Configuration

Example `requirements.txt`:

```text
httpx>=0.27
pendulum>=3
pydantic>=2
tenacity>=8
```

Add provider packages for your destinations:

```text
apache-airflow-providers-amazon
apache-airflow-providers-postgres
apache-airflow-providers-slack
```

Example local-only `airflow_settings.yaml`:

```yaml
airflow:
  variables:
    - variable_name: swpc_stale_after_minutes
      variable_value: "5"
  connections:
    - conn_id: swpc_http
      conn_type: http
      conn_host: https://services.swpc.noaa.gov
```

Use Astronomer deployment configuration for production values rather than
committing real credentials.

## Testing

Minimum tests:

- DAG import test: every DAG parses without scheduler errors.
- Endpoint parser tests using captured NOAA samples.
- Header-row parser test for `/products/solar-wind/*`.
- Classifier tests for G1-G5, S1-S5, and R1-R5 thresholds.
- Idempotency test: parsing the same raw payload twice produces the same curated
  records.
- Staleness test: unchanged payloads return no downstream writes.

Example pytest shape:

```python
def test_noaa_scales_parser(sample_noaa_scales):
    rows = parse_noaa_scales(sample_noaa_scales)
    assert rows
    assert {"date_stamp", "time_stamp", "scale_type", "scale"}.issubset(rows[0])


def test_xray_r_scale_thresholds():
    assert classify_r(9.9e-6) is None
    assert classify_r(1e-5) == "R1"
    assert classify_r(5e-5) == "R2"
    assert classify_r(1e-4) == "R3"
```

## Deployment Flow

1. Initialize an Astro project with `astro dev init`.
2. Put DAG files in `dags/`.
3. Put reusable parser/fetch/classifier code in `include/swpc/`.
4. Add Python dependencies to `requirements.txt`.
5. Add local connections/variables to `airflow_settings.yaml`.
6. Run locally with `astro dev start`.
7. Run unit tests and DAG import tests.
8. Deploy with `astro deploy`.
9. Configure production connections, variables, and secrets in Astronomer.
10. Watch scheduler health, task duration, retry rate, stale endpoint count, and
    scale-transition alerts.

## Operational Checks

Monitor these metrics:

- DAG run duration p50/p95.
- Missed or delayed DAG runs.
- Endpoint `last_success_at` and `last_changed_at`.
- Consecutive fetch failures.
- Rows parsed per endpoint.
- Schema drift warnings.
- Raw-to-curated lag.
- Current official G/R/S scale.
- Official-vs-derived scale disagreement.

Alert when:

- Any critical endpoint is stale for more than 5 minutes.
- The DAG fails more than two consecutive runs.
- NOAA scale increases from none/G1/S1/R1 to a higher state.
- Official and derived scale states disagree for multiple runs.
- Parser validation fails after a payload changed.

## Backfills And Replays

Most SWPC operational endpoints are rolling windows, so do not rely on them for
long historical backfills. Preserve raw payloads as they arrive. For historical
analysis, use archived NOAA/NCEI products when available.

Replay design:

1. Select raw payload URIs by endpoint and fetch time.
2. Run parser and transform code in a separate replay DAG.
3. Write replay output to a temporary schema or partition.
4. Compare row counts and classifications.
5. Promote only after validation.

Keep replay DAGs separate from the minute-level ingestion DAG so historical work
cannot block real-time updates.

## Common Mistakes

- Trying to make Airflow behave like Kafka.
- Passing full JSON payloads through XCom.
- Letting one slow endpoint block every other endpoint.
- Running with `catchup=True` on a one-minute poller.
- Ignoring `ETag` and `Last-Modified`.
- Overwriting raw payloads instead of keeping immutable copies.
- Treating SWPC derived and official scales as identical without labels.
- Alerting every minute while a scale remains active instead of alerting on
  transitions.

## Sources

- [Apache Airflow TaskFlow docs](https://github.com/apache/airflow/blob/main/airflow-core/docs/core-concepts/taskflow.rst):
  TaskFlow API patterns for Python ETL DAGs.
- [Apache Airflow dynamic task mapping docs](https://github.com/apache/airflow/blob/main/task-sdk/docs/dynamic-task-mapping.rst):
  `expand()` pattern for runtime task fan-out.
- [Astronomer DAG best practices](https://www.astronomer.io/docs/learn/dag-best-practices):
  Recommended Astronomer/Airflow project layout and DAG organization.
- [Astronomer Astro CLI project docs](https://www.astronomer.io/docs/astro/cli/develop-project):
  `astro dev init`, local development project structure, and deployment files.
- [NOAA SWPC Products directory](https://services.swpc.noaa.gov/products/):
  Product API reference root used by this pipeline.
