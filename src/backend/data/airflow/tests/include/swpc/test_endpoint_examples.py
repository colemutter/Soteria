from __future__ import annotations

import json
import sys
import unittest
from dataclasses import asdict
from pathlib import Path
from typing import Any


AIRFLOW_ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = AIRFLOW_ROOT.parent
for path in (AIRFLOW_ROOT, DATA_ROOT):
    path_string = str(path)
    if path_string not in sys.path:
        sys.path.insert(0, path_string)

from include.swpc.endpoints import (  # noqa: E402
    ASSET_SPECIFIC_PROTECTION_ENDPOINTS,
    MINIMAL_PROTECTION_ENDPOINTS,
    SWPC_ENDPOINTS,
)
from util.classifier import classify_endpoint, classify_rows, normalize_payload  # noqa: E402


def _official_scale_summary(endpoint: str, payload: Any) -> list[dict[str, Any]]:
    classification = classify_endpoint(endpoint, payload)
    return [
        {
            "scale_family": scale.scale_family,
            "scale": scale.scale,
            "level": scale.level,
            "label": scale.label,
            "derived": scale.derived,
            "source_field": scale.source_field,
            "source_value": scale.source_value,
        }
        for scale in classification.classifications
    ]


EXAMPLE_CASES = [
    {
        "name": "keyed object official scales",
        "endpoint": "/products/noaa-scales.json",
        "before": {
            "-1": {
                "DateStamp": "2026-06-19",
                "TimeStamp": "21:00",
                "R": {"Scale": 1},
                "S": {"Scale": 0},
                "G": {"Scale": 1},
            },
            "0": {
                "DateStamp": "2026-06-20",
                "TimeStamp": "21:00",
                "R": {"Scale": 2},
                "S": {"Scale": 1},
                "G": {"Scale": 3},
            },
        },
        "after": {
            "normalized_rows": [
                {
                    "endpoint": "/products/noaa-scales.json",
                    "DateStamp": "2026-06-19",
                    "TimeStamp": "21:00",
                    "R": {"Scale": 1.0},
                    "S": {"Scale": 0.0},
                    "G": {"Scale": 1.0},
                    "window_offset": -1.0,
                },
                {
                    "endpoint": "/products/noaa-scales.json",
                    "DateStamp": "2026-06-20",
                    "TimeStamp": "21:00",
                    "R": {"Scale": 2.0},
                    "S": {"Scale": 1.0},
                    "G": {"Scale": 3.0},
                    "window_offset": 0.0,
                },
            ],
            "classifications": [
                {
                    "scale_family": "G",
                    "scale": "G3",
                    "level": 3,
                    "label": "G3 Strong",
                    "derived": False,
                    "source_field": "G",
                    "source_value": {"Scale": 3.0},
                },
                {
                    "scale_family": "S",
                    "scale": "S1",
                    "level": 1,
                    "label": "S1 Minor",
                    "derived": False,
                    "source_field": "S",
                    "source_value": {"Scale": 1.0},
                },
                {
                    "scale_family": "R",
                    "scale": "R2",
                    "level": 2,
                    "label": "R2 Moderate",
                    "derived": False,
                    "source_field": "R",
                    "source_value": {"Scale": 2.0},
                },
            ],
        },
    },
    {
        "name": "record array xray measurements",
        "endpoint": "/json/goes/primary/xrays-6-hour.json",
        "before": [
            {
                "time_tag": "2026-06-20 20:59:00",
                "satellite": 18,
                "energy": "0.05-0.4nm",
                "flux": "2.4e-6",
            },
            {
                "time_tag": "2026-06-20 21:00:00",
                "satellite": 18,
                "energy": "0.1-0.8nm",
                "flux": "6.0e-5",
            },
        ],
        "after": {
            "normalized_rows": [
                {
                    "endpoint": "/json/goes/primary/xrays-6-hour.json",
                    "time_tag": "2026-06-20T20:59:00Z",
                    "satellite": 18,
                    "energy": "0.05-0.4nm",
                    "flux": 2.4e-06,
                },
                {
                    "endpoint": "/json/goes/primary/xrays-6-hour.json",
                    "time_tag": "2026-06-20T21:00:00Z",
                    "satellite": 18,
                    "energy": "0.1-0.8nm",
                    "flux": 6e-05,
                    "r_scale": "R2",
                    "r_scale_level": 2,
                    "r_scale_label": "R2 Moderate",
                    "r_scale_source_field": "flux",
                },
            ],
        },
    },
    {
        "name": "header-row solar wind chart",
        "endpoint": "/products/solar-wind/mag-2-hour.json",
        "before": [
            ["time_tag", "bx_gsm", "by_gsm", "bz_gsm", "bt"],
            ["2026-06-20 20:59:00", "1.1", "-2.2", "-8.4", "9.0"],
            ["2026-06-20 21:00:00", "1.0", "-2.5", "-9.1", "9.7"],
        ],
        "after": {
            "normalized_rows": [
                {
                    "endpoint": "/products/solar-wind/mag-2-hour.json",
                    "time_tag": "2026-06-20T20:59:00Z",
                    "bx_gsm": 1.1,
                    "by_gsm": -2.2,
                    "bz_gsm": -8.4,
                    "bt": 9.0,
                },
                {
                    "endpoint": "/products/solar-wind/mag-2-hour.json",
                    "time_tag": "2026-06-20T21:00:00Z",
                    "bx_gsm": 1.0,
                    "by_gsm": -2.5,
                    "bz_gsm": -9.1,
                    "bt": 9.7,
                },
            ],
        },
    },
    {
        "name": "grid object aurora forecast",
        "endpoint": "/json/ovation_aurora_latest.json",
        "before": {
            "Observation Time": "2026-06-20T20:45:00Z",
            "Forecast Time": "2026-06-20T21:15:00Z",
            "Data Format": "[Longitude, Latitude, Aurora]",
            "coordinates": [["-147.5", "64.5", "18"], ["-146.5", "64.5", "22"]],
        },
        "after": {
            "normalized_rows": [
                {
                    "endpoint": "/json/ovation_aurora_latest.json",
                    "Observation Time": "2026-06-20T20:45:00Z",
                    "Forecast Time": "2026-06-20T21:15:00Z",
                    "Data Format": "[Longitude, Latitude, Aurora]",
                    "coordinates": [[-147.5, 64.5, 18.0], [-146.5, 64.5, 22.0]],
                },
            ],
        },
    },
    {
        "name": "message array alerts",
        "endpoint": "/products/alerts.json",
        "before": [
            {
                "product_id": "SUMSUD",
                "issue_datetime": "2026-06-20 21:05:00",
                "message": "Space Weather Message Code: SUMSUD",
            }
        ],
        "after": {
            "normalized_rows": [
                {
                    "endpoint": "/products/alerts.json",
                    "product_id": "SUMSUD",
                    "issue_datetime": "2026-06-20T21:05:00Z",
                    "message": "Space Weather Message Code: SUMSUD",
                }
            ],
        },
    },
]


class SwpcEndpointExamplesTest(unittest.TestCase):
    def test_catalog_contains_minimal_then_asset_specific_endpoints(self) -> None:
        before = [endpoint.path for endpoint in SWPC_ENDPOINTS]
        after = [asdict(endpoint) for endpoint in SWPC_ENDPOINTS]

        self.assertEqual(len(MINIMAL_PROTECTION_ENDPOINTS), 9)
        self.assertEqual(len(ASSET_SPECIFIC_PROTECTION_ENDPOINTS), 10)
        self.assertEqual(len(SWPC_ENDPOINTS), 19)
        self.assertEqual(
            before[:3],
            [
                "/products/noaa-scales.json",
                "/products/alerts.json",
                "/json/rtsw/rtsw_mag_1m.json",
            ],
        )
        self.assertTrue(
            all(
                endpoint["protection_tier"] == "minimal"
                for endpoint in after[: len(MINIMAL_PROTECTION_ENDPOINTS)]
            )
        )
        self.assertTrue(
            all(
                endpoint["protection_tier"] == "asset_specific"
                for endpoint in after[len(MINIMAL_PROTECTION_ENDPOINTS) :]
            )
        )

    def test_example_payloads_show_before_and_after_outputs(self) -> None:
        examples = []

        for case in EXAMPLE_CASES:
            endpoint = case["endpoint"]
            before = case["before"]

            if "classifications" in case["after"]:
                actual_after = {
                    "normalized_rows": normalize_payload(before, endpoint=endpoint),
                    "classifications": _official_scale_summary(endpoint, before),
                }
            elif "xrays" in endpoint:
                actual_after = {
                    "normalized_rows": classify_rows(endpoint, before),
                }
            else:
                actual_after = {
                    "normalized_rows": normalize_payload(before, endpoint=endpoint),
                }

            examples.append(
                {
                    "format": case["name"],
                    "endpoint": endpoint,
                    "before": before,
                    "after": actual_after,
                }
            )
            self.assertEqual(actual_after, case["after"])

        print(json.dumps(examples, indent=2, sort_keys=True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
