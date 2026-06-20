from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pendulum
from airflow.decorators import dag, task

AIRFLOW_ROOT = Path(__file__).resolve().parents[1]
if str(AIRFLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(AIRFLOW_ROOT))

from include.neon_db_writer import NeonDbWriter
from include.swpc.endpoints import SWPC_ENDPOINTS
from include.swpc.pipeline import ingest_endpoint, setup_database, summarize_ingest


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
    def setup_swpc_database() -> str:
        writer = NeonDbWriter()
        setup_database(writer)
        return "ready"

    @task
    def load_endpoint_config() -> list[dict[str, object]]:
        return [
            {
                "path": endpoint.path,
                "family": endpoint.family,
                "cadence_seconds": endpoint.cadence_seconds,
                "protection_tier": endpoint.protection_tier,
            }
            for endpoint in SWPC_ENDPOINTS
        ]

    @task(pool="swpc_http")
    def ingest_swpc_endpoint(endpoint: dict[str, object]) -> dict[str, object]:
        writer = NeonDbWriter()
        return ingest_endpoint(writer, endpoint).to_dict()

    @task
    def publish_current_state(results: list[dict[str, object]]) -> dict[str, object]:
        summary = summarize_ingest(results)
        summary["published_at"] = pendulum.now("UTC").to_iso8601_string()
        return summary

    @task
    def emit_scale_transition_alerts(current_state: dict[str, object]) -> None:
        # Replace this with Slack, PagerDuty, email, or app notifications.
        # Alert only on scale transitions, not every minute.
        print(current_state)

    database_ready = setup_swpc_database()
    endpoints = load_endpoint_config()
    ingest_results = ingest_swpc_endpoint.expand(endpoint=endpoints)
    database_ready >> ingest_results
    current_state = publish_current_state(ingest_results)
    emit_scale_transition_alerts(current_state)


dag = swpc_realtime_etl()
