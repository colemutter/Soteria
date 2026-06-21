from __future__ import annotations

from include.supabase_swpc_writer import SupabaseSwpcWriter
from include.swpc.event_windows import (
    EVENT_WINDOW_PRODUCT_TYPES,
    derive_space_weather_event_windows,
    summarize_event_windows,
)


import datetime as dt
import sys
from pathlib import Path

import pendulum
from airflow.sdk import dag, task

AIRFLOW_ROOT = Path(__file__).resolve().parents[1]
if str(AIRFLOW_ROOT) not in sys.path:
    sys.path.insert(0, str(AIRFLOW_ROOT))




@dag(
    dag_id="swpc_event_window_etl",
    schedule=None,
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=dt.timedelta(minutes=2),
    default_args={"retries": 2, "retry_delay": dt.timedelta(seconds=15)},
    tags=["swpc", "space-weather", "event-windows"],
)
def swpc_event_window_etl():
    @task
    def derive_and_publish_event_windows() -> dict[str, object]:
        writer = SupabaseSwpcWriter()
        now = pendulum.now("UTC")
        since = now.subtract(days=1).to_iso8601_string()
        records = writer.list_forecast_records(
            product_types=EVENT_WINDOW_PRODUCT_TYPES,
            valid_start_gte=since,
        )
        windows = derive_space_weather_event_windows(
            records,
            now=now,
        )
        writer.upsert_event_windows(windows)
        summary = summarize_event_windows(windows)
        summary["source_record_count"] = len(records)
        summary["published_at"] = now.to_iso8601_string()
        return summary

    @task
    def emit_event_window_summary(summary: dict[str, object]) -> None:
        print(summary)

    emit_event_window_summary(derive_and_publish_event_windows())


dag = swpc_event_window_etl()
