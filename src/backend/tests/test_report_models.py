from __future__ import annotations

import datetime as dt
import unittest

from pydantic import ValidationError

from agent.report_models import (
    EventWindowReportBatch,
    EventWindowSatelliteReport,
    EventWindowEvidence,
    ReportEvidenceBundle,
    ReportSeverity,
    SatelliteEvidence,
    SatelliteOutcome,
    report_validation_context,
)


NOW = dt.datetime(2026, 6, 21, 12, 0, tzinfo=dt.UTC)


def evidence_bundle() -> ReportEvidenceBundle:
    return ReportEvidenceBundle(
        event_window=EventWindowEvidence(
            id="ew_123",
            event_key="geomagnetic:2026-06-21T12:00:00Z",
            event_type="geomagnetic_storm_risk",
            source_product="swpc_kp_forecast",
            status="active",
            confidence="high",
            window_start=NOW,
            window_end=NOW + dt.timedelta(hours=6),
            updated_at=NOW,
            peak_severity=3,
            evidence={"kp": 7},
        ),
        satellites=[
            SatelliteEvidence(
                external_id="real-25544",
                name="ISS (ZARYA)",
                orbit_regime="LEO",
                operational_status="active",
                norad_cat_id=25544,
                updated_at=NOW,
            )
        ],
        evidence_hash="hash_123",
        created_at=NOW,
    )


def valid_report_payload() -> dict:
    return {
        "event_window_id": "ew_123",
        "evidence_hash": "hash_123",
        "event_severity": "major",
        "summary": "Geomagnetic activity may increase LEO drag.",
        "possible_outcomes": ["increased_drag", "orbit_prediction_degraded"],
        "findings": [
            {
                "satellite_id": "real-25544",
                "severity": "major",
                "possible_outcomes": ["increased_drag"],
                "rationale": "LEO spacecraft are sensitive to density increases.",
                "source_event_window_ids": ["ew_123"],
                "source_satellite_ids": ["real-25544"],
            }
        ],
        "confidence": "medium",
    }


class ReportModelsTest(unittest.TestCase):
    def test_valid_report_passes_with_evidence_context(self) -> None:
        bundle = evidence_bundle()

        report = EventWindowSatelliteReport.model_validate(
            valid_report_payload(),
            context=report_validation_context(bundle),
        )

        self.assertEqual(report.event_severity, ReportSeverity.MAJOR)
        self.assertEqual(
            report.possible_outcomes,
            [
                SatelliteOutcome.INCREASED_DRAG,
                SatelliteOutcome.ORBIT_PREDICTION_DEGRADED,
            ],
        )

    def test_invalid_severity_fails_validation(self) -> None:
        payload = valid_report_payload()
        payload["event_severity"] = "catastrophic"

        with self.assertRaises(ValidationError):
            EventWindowSatelliteReport.model_validate(
                payload,
                context=report_validation_context(evidence_bundle()),
            )

    def test_invalid_outcome_fails_validation(self) -> None:
        payload = valid_report_payload()
        payload["possible_outcomes"] = ["mystery_effect"]

        with self.assertRaises(ValidationError):
            EventWindowSatelliteReport.model_validate(
                payload,
                context=report_validation_context(evidence_bundle()),
            )

    def test_missing_event_window_citation_fails_validation(self) -> None:
        payload = valid_report_payload()
        payload["findings"][0]["source_event_window_ids"] = ["ew_missing"]

        with self.assertRaisesRegex(ValidationError, "unknown event_window_ids"):
            EventWindowSatelliteReport.model_validate(
                payload,
                context=report_validation_context(evidence_bundle()),
            )

    def test_missing_satellite_citation_fails_validation(self) -> None:
        payload = valid_report_payload()
        payload["findings"][0]["source_satellite_ids"] = ["real-missing"]

        with self.assertRaisesRegex(ValidationError, "unknown satellite_ids"):
            EventWindowSatelliteReport.model_validate(
                payload,
                context=report_validation_context(evidence_bundle()),
            )

    def test_unexpected_extra_fields_fail_validation(self) -> None:
        payload = valid_report_payload()
        payload["new_ai_field"] = "not allowed"

        with self.assertRaises(ValidationError):
            EventWindowSatelliteReport.model_validate(
                payload,
                context=report_validation_context(evidence_bundle()),
            )

    def test_batch_requires_one_report_for_each_event_window(self) -> None:
        with self.assertRaisesRegex(ValidationError, "missing=\\['ew_456'\\]"):
            EventWindowReportBatch.model_validate(
                {"reports": [valid_report_payload()]},
                context={
                    **report_validation_context(evidence_bundle()),
                    "event_window_ids": {"ew_123", "ew_456"},
                },
            )


if __name__ == "__main__":
    unittest.main()
