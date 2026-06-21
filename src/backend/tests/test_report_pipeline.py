from __future__ import annotations

import datetime as dt
import unittest
from typing import Any

from agent.report_models import ReportSeverity, SatelliteOutcome
from agent.report_pipeline import (
    build_report_evidence_bundles,
    evidence_hash_for_bundle,
    resolve_event_windows,
)


NOW = dt.datetime(2026, 6, 21, 12, 0, tzinfo=dt.UTC)


def event_row(event_window_id: str, *, event_key: str | None = None) -> dict[str, Any]:
    return {
        "id": event_window_id,
        "event_key": event_key or f"geomagnetic:{event_window_id}",
        "event_type": "geomagnetic_storm_risk",
        "source_product": "swpc_kp_forecast",
        "source_endpoint": "https://example.test/swpc",
        "window_start": NOW.isoformat(),
        "peak_time": NOW.isoformat(),
        "window_end": (NOW + dt.timedelta(hours=6)).isoformat(),
        "peak_value": 7.0,
        "peak_severity": 3,
        "threshold_value": 5.0,
        "units": "Kp",
        "confidence": "high",
        "status": "active",
        "evidence": {"kp": 7},
        "updated_at": NOW.isoformat(),
    }


def satellite_row(
    external_id: str = "real-25544",
    *,
    orbit_regime: str = "LEO",
    altitude_km: float = 420.0,
) -> dict[str, Any]:
    return {
        "external_id": external_id,
        "norad_cat_id": 25544,
        "name": "ISS (ZARYA)",
        "operator": "NASA",
        "country": "US",
        "mission_class": "human_spaceflight",
        "operational_status": "active",
        "orbit_regime": orbit_regime,
        "tle_epoch": NOW.isoformat(),
        "reference_epoch": NOW.isoformat(),
        "mass_kg": 419725,
        "cross_section_area_m2": 400.0,
        "drag_coefficient": 2.2,
        "ballistic_coefficient_kg_m2": 476.9,
        "position_time": NOW.isoformat(),
        "latitude_deg": 1.0,
        "longitude_deg": 2.0,
        "altitude_km": altitude_km,
        "speed_km_s": 7.66,
        "updated_at": NOW.isoformat(),
    }


class FakeQuery:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data
        self.calls: list[tuple[str, Any]] = []

    def select(self, columns: str):
        self.calls.append(("select", columns))
        return self

    def in_(self, column: str, values: list[Any]):
        self.calls.append(("in_", (column, values)))
        return self

    def eq(self, column: str, value: Any):
        self.calls.append(("eq", (column, value)))
        return self

    def order(self, column: str):
        self.calls.append(("order", column))
        return self

    def limit(self, value: int):
        self.calls.append(("limit", value))
        return self

    def execute(self):
        rows = self.data
        for method, payload in self.calls:
            if method == "in_":
                column, values = payload
                rows = [row for row in rows if row.get(column) in values]
            if method == "eq":
                column, value = payload
                rows = [row for row in rows if row.get(column) == value]
        return type("Response", (), {"data": rows})()


class FakeClient:
    def __init__(
        self,
        *,
        event_windows: list[dict[str, Any]],
        satellites: list[dict[str, Any]] | None = None,
    ) -> None:
        self.queries = {
            "space_weather_event_windows": FakeQuery(event_windows),
            "satellites": FakeQuery(satellites or []),
        }

    def table(self, name: str) -> FakeQuery:
        return self.queries[name]


class ReportPipelineTest(unittest.TestCase):
    def test_resolve_event_windows_all_found(self) -> None:
        client = FakeClient(event_windows=[event_row("ew_1"), event_row("ew_2")])

        result = resolve_event_windows(["ew_1", "ew_2"], client)

        self.assertFalse(result.failed_closed)
        self.assertEqual([row.id for row in result.resolved_event_windows], ["ew_1", "ew_2"])
        self.assertEqual(result.missing_event_window_ids, [])
        self.assertIn(
            ("in_", ("id", ["ew_1", "ew_2"])),
            client.queries["space_weather_event_windows"].calls,
        )

    def test_resolve_event_windows_partially_missing(self) -> None:
        client = FakeClient(event_windows=[event_row("ew_1")])

        result = resolve_event_windows(["ew_1", "ew_missing"], client)

        self.assertFalse(result.failed_closed)
        self.assertEqual([row.id for row in result.resolved_event_windows], ["ew_1"])
        self.assertEqual(result.missing_event_window_ids, ["ew_missing"])

    def test_resolve_event_windows_all_missing_fails_closed(self) -> None:
        client = FakeClient(event_windows=[])

        result = resolve_event_windows(["ew_missing"], client)

        self.assertTrue(result.failed_closed)
        self.assertEqual(result.resolved_event_windows, [])
        self.assertEqual(result.missing_event_window_ids, ["ew_missing"])
        self.assertTrue(
            any("no requested event_window_ids resolved" in error for error in result.validation_errors)
        )

    def test_resolve_event_windows_dedupes_duplicate_ids(self) -> None:
        client = FakeClient(event_windows=[event_row("ew_1")])

        result = resolve_event_windows(["ew_1", "ew_1", "ew_1"], client)

        self.assertFalse(result.failed_closed)
        self.assertEqual(result.requested_event_window_ids, ["ew_1"])
        self.assertEqual(result.duplicate_event_window_ids, ["ew_1", "ew_1"])
        self.assertEqual([row.id for row in result.resolved_event_windows], ["ew_1"])
        self.assertIn(
            ("in_", ("id", ["ew_1"])),
            client.queries["space_weather_event_windows"].calls,
        )

    def test_resolve_event_windows_malformed_row_fails_validation(self) -> None:
        malformed = event_row("ew_1")
        malformed.pop("event_key")
        client = FakeClient(event_windows=[malformed])

        result = resolve_event_windows(["ew_1"], client)

        self.assertTrue(result.failed_closed)
        self.assertEqual(result.resolved_event_windows, [])
        self.assertTrue(
            any("event_window_id=ew_1 failed validation" in error for error in result.validation_errors)
        )

    def test_builds_one_event_one_satellite_bundle(self) -> None:
        client = FakeClient(
            event_windows=[event_row("ew_1")],
            satellites=[satellite_row()],
        )

        result = build_report_evidence_bundles(["ew_1"], client, created_at=NOW)

        self.assertFalse(result.failed_closed)
        self.assertEqual(result.resolved_event_window_ids, ["ew_1"])
        self.assertEqual(len(result.bundles), 1)
        bundle = result.bundles[0]
        self.assertEqual(bundle.event_window.id, "ew_1")
        self.assertEqual([sat.external_id for sat in bundle.satellites], ["real-25544"])
        self.assertEqual(bundle.allowed_severities, list(ReportSeverity))
        self.assertEqual(bundle.allowed_outcomes, list(SatelliteOutcome))
        self.assertEqual(len(bundle.evidence_hash), 64)
        self.assertIn(
            ("eq", ("operational_status", "active")),
            client.queries["satellites"].calls,
        )
        self.assertEqual(
            bundle.impact_guidance[0].likely_outcomes[:2],
            [
                SatelliteOutcome.INCREASED_DRAG,
                SatelliteOutcome.ORBIT_PREDICTION_DEGRADED,
            ],
        )
        self.assertIn("geomagnetic", bundle.satellite_selection_notes[0])

    def test_builds_multiple_event_bundles(self) -> None:
        client = FakeClient(
            event_windows=[event_row("ew_2"), event_row("ew_1")],
            satellites=[satellite_row()],
        )

        result = build_report_evidence_bundles(["ew_1", "ew_2"], client, created_at=NOW)

        self.assertFalse(result.failed_closed)
        self.assertEqual(result.resolved_event_window_ids, ["ew_1", "ew_2"])
        self.assertEqual([bundle.event_window.id for bundle in result.bundles], ["ew_1", "ew_2"])

    def test_builds_bundle_with_no_active_satellites(self) -> None:
        client = FakeClient(
            event_windows=[event_row("ew_1")],
            satellites=[{**satellite_row(), "operational_status": "retired"}],
        )

        result = build_report_evidence_bundles(["ew_1"], client, created_at=NOW)

        self.assertFalse(result.failed_closed)
        self.assertEqual(len(result.bundles), 1)
        self.assertEqual(result.bundles[0].satellites, [])

    def test_evidence_hash_is_stable_for_same_evidence(self) -> None:
        client_a = FakeClient(
            event_windows=[event_row("ew_1")],
            satellites=[satellite_row("real-b"), satellite_row("real-a")],
        )
        client_b = FakeClient(
            event_windows=[event_row("ew_1")],
            satellites=[satellite_row("real-a"), satellite_row("real-b")],
        )

        result_a = build_report_evidence_bundles(["ew_1"], client_a, created_at=NOW)
        result_b = build_report_evidence_bundles(
            ["ew_1"],
            client_b,
            created_at=NOW + dt.timedelta(minutes=5),
        )

        self.assertEqual(result_a.bundles[0].evidence_hash, result_b.bundles[0].evidence_hash)
        self.assertEqual(
            result_a.bundles[0].evidence_hash,
            evidence_hash_for_bundle(
                event_window=result_a.bundles[0].event_window,
                satellites=result_a.bundles[0].satellites,
                source_refs=result_a.bundles[0].source_refs,
                impact_guidance=result_a.bundles[0].impact_guidance,
                satellite_selection_notes=result_a.bundles[0].satellite_selection_notes,
            ),
        )

    def test_geomagnetic_bundle_filters_irrelevant_unknown_orbit_satellites(self) -> None:
        client = FakeClient(
            event_windows=[event_row("ew_1")],
            satellites=[
                satellite_row("leo-low", orbit_regime="LEO", altitude_km=390),
                satellite_row("geo-asset", orbit_regime="GEO", altitude_km=35786),
                satellite_row("unknown-asset", orbit_regime="UNKNOWN", altitude_km=900),
            ],
        )

        result = build_report_evidence_bundles(["ew_1"], client, created_at=NOW)

        self.assertEqual(
            [satellite.external_id for satellite in result.bundles[0].satellites],
            ["leo-low", "geo-asset"],
        )
        reasons = [
            guidance.relevance_reason for guidance in result.bundles[0].impact_guidance
        ]
        self.assertEqual(
            reasons,
            [
                "geomagnetic_leo_drag_and_tracking",
                "geomagnetic_high_orbit_charging",
            ],
        )

    def test_relevant_satellite_cap_limits_report_size(self) -> None:
        client = FakeClient(
            event_windows=[event_row("ew_1")],
            satellites=[
                satellite_row(f"leo-{index}", orbit_regime="LEO", altitude_km=410)
                for index in range(5)
            ],
        )

        result = build_report_evidence_bundles(
            ["ew_1"],
            client,
            created_at=NOW,
            max_relevant_satellites=2,
        )

        bundle = result.bundles[0]
        self.assertEqual(len(bundle.satellites), 2)
        self.assertIn("Selected top 2 of 5", bundle.satellite_selection_notes[-1])


if __name__ == "__main__":
    unittest.main()
