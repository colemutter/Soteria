from __future__ import annotations

import sys
import unittest
from pathlib import Path


AIRFLOW_ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = AIRFLOW_ROOT.parent
for path in (AIRFLOW_ROOT, DATA_ROOT):
    path_string = str(path)
    if path_string not in sys.path:
        sys.path.insert(0, path_string)

from include.swpc.forecast_records import normalize_forecast_records  # noqa: E402


class SwpcForecastRecordsTest(unittest.TestCase):
    def test_noaa_scales_emit_one_record_per_family_and_window(self) -> None:
        payload = {
            "0": {
                "DateStamp": "2026-06-20",
                "TimeStamp": "21:00",
                "R": {"Scale": 2},
                "S": {"Scale": 0},
                "G": {"Scale": 3},
            },
            "1": {
                "DateStamp": "2026-06-21",
                "TimeStamp": "21:00",
                "R": {"Scale": 1},
                "S": {"Scale": 0},
                "G": {"Scale": 2},
            },
        }

        rows = normalize_forecast_records(
            "/products/noaa-scales.json",
            payload,
            "2026-06-20T21:01:00Z",
            raw_payload_id="raw-1",
            source="swpc",
        )

        self.assertEqual(len(rows), 6)
        current_g = next(row for row in rows if row["product_type"] == "noaa_scale_g")
        self.assertEqual(current_g["valid_start"], "2026-06-20T21:00:00Z")
        self.assertEqual(current_g["valid_end"], "2026-06-21T21:00:00Z")
        self.assertEqual(current_g["observed"], True)
        self.assertEqual(current_g["severity"], 3)
        self.assertEqual(current_g["value"], 3)
        self.assertEqual(current_g["units"], "NOAA G scale")
        self.assertEqual(current_g["record"]["scale"], "G3")
        self.assertEqual(current_g["raw_payload_id"], "raw-1")
        self.assertEqual(current_g["source"], "swpc")
        self.assertRegex(current_g["record_hash"], r"^[0-9a-f]{64}$")

        future_g = [
            row
            for row in rows
            if row["product_type"] == "noaa_scale_g"
            and row["valid_start"] == "2026-06-21T21:00:00Z"
        ][0]
        self.assertEqual(future_g["observed"], False)

    def test_kp_forecast_header_rows_have_three_hour_windows(self) -> None:
        payload = [
            ["time_tag", "kp", "observed", "noaa_scale"],
            ["2026-06-20 21:00:00", "5-", "true", "G1"],
            ["2026-06-21 00:00:00", "6", "false", "G2"],
        ]

        rows = normalize_forecast_records(
            "/products/noaa-planetary-k-index-forecast.json",
            payload,
            "2026-06-20T21:05:00Z",
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["product_type"], "kp_forecast")
        self.assertEqual(rows[0]["valid_start"], "2026-06-20T21:00:00Z")
        self.assertEqual(rows[0]["valid_end"], "2026-06-21T00:00:00Z")
        self.assertEqual(rows[0]["observed"], True)
        self.assertAlmostEqual(rows[0]["value"], 4.666666666666667)
        self.assertEqual(rows[0]["severity"], 1)
        self.assertEqual(rows[0]["units"], "Kp")

        self.assertEqual(rows[1]["valid_start"], "2026-06-21T00:00:00Z")
        self.assertEqual(rows[1]["valid_end"], "2026-06-21T03:00:00Z")
        self.assertEqual(rows[1]["observed"], False)
        self.assertEqual(rows[1]["value"], 6.0)
        self.assertEqual(rows[1]["severity"], 2)

    def test_alerts_use_issue_datetime_as_issue_and_valid_start(self) -> None:
        payload = [
            {
                "product_id": "WARK04",
                "issue_datetime": "2026-06-20 21:05:00",
                "message": "Space Weather Message Code: WARK04\nG2 Watch in effect.",
            }
        ]

        rows = normalize_forecast_records(
            "/products/alerts.json",
            payload,
            "2026-06-20T21:06:00Z",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["product_type"], "alert")
        self.assertEqual(rows[0]["issued_at"], "2026-06-20T21:05:00Z")
        self.assertEqual(rows[0]["valid_start"], "2026-06-20T21:05:00Z")
        self.assertIsNone(rows[0]["valid_end"])
        self.assertEqual(rows[0]["severity"], 2)
        self.assertEqual(rows[0]["record"]["product_id"], "WARK04")

    def test_solar_wind_mag_chart_rows_emit_event_window_metrics(self) -> None:
        payload = [
            ["time_tag", "bx_gsm", "by_gsm", "bz_gsm", "bt"],
            ["2026-06-20 21:00:00", "1.0", "-2.5", "-9.1", "9.7"],
        ]

        rows = normalize_forecast_records(
            "/products/solar-wind/mag-2-hour.json",
            payload,
            "2026-06-20T21:01:00Z",
        )

        self.assertEqual(
            [row["product_type"] for row in rows],
            ["solar_wind_mag_bz_gsm", "solar_wind_mag_bt"],
        )
        self.assertEqual(rows[0]["valid_start"], "2026-06-20T21:00:00Z")
        self.assertEqual(rows[0]["observed"], True)
        self.assertEqual(rows[0]["value"], -9.1)
        self.assertEqual(rows[0]["units"], "nT")
        self.assertEqual(rows[0]["record"]["metric"], "bz_gsm")
        self.assertEqual(rows[1]["value"], 9.7)

    def test_record_hash_is_stable_across_fetch_metadata(self) -> None:
        payload = [
            {
                "time_tag": "2026-06-20 21:00:00",
                "Kp": "5",
                "station_count": "8",
            }
        ]

        first = normalize_forecast_records(
            "/products/noaa-planetary-k-index.json",
            payload,
            "2026-06-20T21:01:00Z",
            raw_payload_id="raw-1",
        )
        second = normalize_forecast_records(
            "/products/noaa-planetary-k-index.json",
            payload,
            "2026-06-20T21:02:00Z",
            raw_payload_id="raw-2",
        )

        self.assertEqual(first[0]["record_hash"], second[0]["record_hash"])
        self.assertNotEqual(first[0]["raw_payload_id"], second[0]["raw_payload_id"])
        self.assertNotEqual(first[0]["fetched_at"], second[0]["fetched_at"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
