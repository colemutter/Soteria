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

from include.swpc.event_windows import derive_space_weather_event_windows  # noqa: E402


class SwpcEventWindowsTest(unittest.TestCase):
    def test_merges_adjacent_kp_forecast_bins_into_geomagnetic_window(self) -> None:
        records = [
            {
                "id": "r1",
                "endpoint": "/products/noaa-planetary-k-index-forecast.json",
                "product_type": "kp_forecast",
                "valid_start": "2026-06-21T00:00:00Z",
                "valid_end": "2026-06-21T03:00:00Z",
                "observed": False,
                "severity": 1,
                "value": 5,
                "units": "Kp",
                "fetched_at": "2026-06-20T22:00:00Z",
            },
            {
                "id": "r2",
                "endpoint": "/products/noaa-planetary-k-index-forecast.json",
                "product_type": "kp_forecast",
                "valid_start": "2026-06-21T03:00:00Z",
                "valid_end": "2026-06-21T06:00:00Z",
                "observed": False,
                "severity": 2,
                "value": 6,
                "units": "Kp",
                "fetched_at": "2026-06-20T22:00:00Z",
            },
        ]

        windows = derive_space_weather_event_windows(
            records,
            now="2026-06-20T22:30:00Z",
        )

        self.assertEqual(len(windows), 1)
        window = windows[0]
        self.assertEqual(window["event_type"], "geomagnetic_storm_risk")
        self.assertEqual(window["window_start"], "2026-06-21T00:00:00Z")
        self.assertEqual(window["window_end"], "2026-06-21T06:00:00Z")
        self.assertEqual(window["peak_time"], "2026-06-21T03:00:00Z")
        self.assertEqual(window["peak_severity"], 2)
        self.assertEqual(window["confidence"], "forecast")
        self.assertEqual(window["status"], "future")
        self.assertRegex(window["event_key"], r"^[0-9a-f]{64}$")

    def test_observed_southward_bz_creates_solar_wind_coupling_window(self) -> None:
        records = [
            {
                "id": "bz-1",
                "endpoint": "/json/rtsw/rtsw_mag_1m.json",
                "product_type": "solar_wind_mag_bz_gsm",
                "valid_start": "2026-06-20T22:00:00Z",
                "observed": True,
                "value": -8.2,
                "units": "nT",
                "fetched_at": "2026-06-20T22:01:00Z",
            },
            {
                "id": "bt-1",
                "endpoint": "/json/rtsw/rtsw_mag_1m.json",
                "product_type": "solar_wind_mag_bt",
                "valid_start": "2026-06-20T22:00:00Z",
                "observed": True,
                "value": 13.4,
                "units": "nT",
                "fetched_at": "2026-06-20T22:01:00Z",
            },
        ]

        windows = derive_space_weather_event_windows(
            records,
            now="2026-06-20T22:00:30Z",
        )

        self.assertEqual(len(windows), 1)
        window = windows[0]
        self.assertEqual(window["event_type"], "solar_wind_coupling_risk")
        self.assertEqual(window["window_start"], "2026-06-20T22:00:00Z")
        self.assertEqual(window["window_end"], "2026-06-20T22:01:00Z")
        self.assertEqual(window["peak_value"], -8.2)
        self.assertEqual(window["confidence"], "observed")
        self.assertEqual(window["status"], "active")

    def test_stale_source_marks_event_window_stale(self) -> None:
        records = [
            {
                "id": "r1",
                "endpoint": "/products/noaa-scales.json",
                "product_type": "noaa_scale_s",
                "valid_start": "2026-06-20T00:00:00Z",
                "valid_end": "2026-06-21T00:00:00Z",
                "observed": False,
                "severity": 1,
                "value": 1,
                "units": "NOAA S scale",
                "fetched_at": "2026-06-20T00:00:00Z",
            }
        ]

        windows = derive_space_weather_event_windows(
            records,
            now="2026-06-20T12:00:00Z",
        )

        self.assertEqual(windows[0]["event_type"], "radiation_storm_risk")
        self.assertEqual(windows[0]["confidence"], "stale")


if __name__ == "__main__":
    unittest.main(verbosity=2)
