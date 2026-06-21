from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pendulum
from airflow.sdk import dag, task
from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator

AIRFLOW_ROOT = Path(__file__).resolve().parents[1]
if str(AIRFLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(AIRFLOW_ROOT))

from include.supabase_swpc_writer import SupabaseSwpcWriter
from include.swpc.endpoints import SWPC_ENDPOINTS
from include.swpc.pipeline import ingest_endpoint, summarize_ingest

RUN_TIMEOUT = dt.timedelta(minutes=30)
RETRY_DELAY = dt.timedelta(seconds=10)
RETRIES = 2



@dag(
    dag_id="swpc_realtime_etl",
    schedule="*/30 * * * *",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=RUN_TIMEOUT,
    default_args={"retries": RETRIES, "retry_delay": RETRY_DELAY},
    tags=["swpc", "space-weather", "near-real-time"],
)
def swpc_realtime_etl():
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

    @task(max_active_tis_per_dag=4)
    def ingest_swpc_endpoint(endpoint: dict[str, object]) -> dict[str, object]:
        writer = SupabaseSwpcWriter()
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

    endpoints = load_endpoint_config()
    ingest_results = ingest_swpc_endpoint.expand(endpoint=endpoints)
    current_state = publish_current_state(ingest_results)
    alert_task = emit_scale_transition_alerts(current_state)
    derive_event_windows = TriggerDagRunOperator(
        task_id="trigger_event_window_etl",
        trigger_dag_id="swpc_event_window_etl",
        trigger_run_id="swpc_event_window__{{ run_id }}",
        conf={"source_dag_run_id": "{{ run_id }}"},
        reset_dag_run=True,
        wait_for_completion=True,
    )
    alert_task >> derive_event_windows


dag = swpc_realtime_etl()
