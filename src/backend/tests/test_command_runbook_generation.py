from __future__ import annotations

import unittest

from agent.command_policy import POLICY_VERSION
from agent.command_runbook_generation import (
    NO_FINDING_REASON,
    RUNBOOK_SOURCE,
    generate_command_runbooks_for_report,
    generate_command_runbooks_for_reports,
)
from agent.command_runbook_persistence import validate_catalog_backed_runbook
from agent.report_models import (
    EventWindowSatelliteReport,
    ReportSeverity,
    SatelliteEvidence,
    SatelliteImpactFinding,
    SatelliteOutcome,
)


def finding(
    satellite_id: str,
    *outcomes: SatelliteOutcome,
    severity: ReportSeverity = ReportSeverity.MAJOR,
    rationale: str = "Solar weather may affect this satellite.",
    event_window_id: str = "ew-1",
) -> SatelliteImpactFinding:
    return SatelliteImpactFinding(
        satellite_id=satellite_id,
        severity=severity,
        possible_outcomes=list(outcomes),
        rationale=rationale,
        source_event_window_ids=[event_window_id],
        source_satellite_ids=[satellite_id],
    )


def report_with_findings(
    *findings: SatelliteImpactFinding,
    event_window_id: str = "ew-1",
    evidence_hash: str = "evidence-hash-1",
) -> EventWindowSatelliteReport:
    possible_outcomes = [
        outcome
        for satellite_finding in findings
        for outcome in satellite_finding.possible_outcomes
    ]
    return EventWindowSatelliteReport(
        event_window_id=event_window_id,
        evidence_hash=evidence_hash,
        event_severity=ReportSeverity.MAJOR,
        summary="Solar weather report for active satellites.",
        possible_outcomes=possible_outcomes,
        findings=list(findings),
        confidence="medium",
    )


def active_satellites() -> list[dict[str, object]]:
    return [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "external_id": "sat-1",
            "name": "PayloadSat",
            "orbit_regime": "LEO",
            "operational_status": "active",
            "supports_sample_payload": True,
        },
        {
            "id": "22222222-2222-2222-2222-222222222222",
            "external_id": "sat-2",
            "name": "DragSat",
            "orbit_regime": "LEO",
            "operational_status": "active",
        },
        {
            "id": "33333333-3333-3333-3333-333333333333",
            "external_id": "sat-3",
            "name": "QuietSat",
            "orbit_regime": "LEO",
            "operational_status": "active",
        },
    ]


class CommandRunbookGenerationTest(unittest.TestCase):
    def test_generates_one_valid_runbook_for_every_satellite_in_scope(self) -> None:
        report = report_with_findings(
            finding("sat-1", SatelliteOutcome.PAYLOAD_NOISE),
            finding("sat-2", SatelliteOutcome.INCREASED_DRAG),
        )

        rows = generate_command_runbooks_for_report(
            report,
            active_satellites(),
            report_id="report-row-1",
        )

        self.assertEqual(len(rows), 3)
        self.assertEqual(
            {row["satellite_external_id"] for row in rows},
            {"sat-1", "sat-2", "sat-3"},
        )
        for row in rows:
            validate_catalog_backed_runbook(row)
            self.assertEqual(row["report_id"], "report-row-1")
            self.assertEqual(row["event_window_id"], "ew-1")
            self.assertEqual(row["evidence_hash"], "evidence-hash-1")
            self.assertEqual(row["policy_version"], POLICY_VERSION)
            self.assertEqual(row["source"], RUNBOOK_SOURCE)
            self.assertTrue(row["catalog_version"])
            self.assertIn(row["satellite_external_id"], row["dedupe_key"])

    def test_command_bearing_runbook_uses_catalog_renderer_and_provenance(self) -> None:
        report = report_with_findings(
            finding("sat-1", SatelliteOutcome.PAYLOAD_NOISE),
        )

        rows = generate_command_runbooks_for_report(
            report,
            active_satellites(),
            report_id="report-row-1",
        )
        generated = self._row_for_satellite(rows, "sat-1")

        self.assertEqual(generated["status"], "generated")
        self.assertEqual(generated["risk_level"], "low")
        self.assertEqual(
            [command["catalog_command_id"] for command in generated["commands"]],
            ["sample_disable"],
        )
        command = generated["commands"][0]
        self.assertEqual(command["target"], "SAMPLE_RADIO")
        self.assertEqual(command["command"], "SAMPLE_DISABLE_CC")
        self.assertEqual(command["args"], [])
        self.assertFalse(command["human_review_required"])
        self.assertTrue(command["automated_allowed"])
        self.assertEqual(command["script_language"], "ruby")
        self.assertIn('cmd("SAMPLE_RADIO SAMPLE_DISABLE_CC")', command["rendered_script"])
        self.assertEqual(
            generated["metadata"]["provenance"]["report_summary"],
            "Solar weather report for active satellites.",
        )
        self.assertEqual(
            generated["metadata"]["selected_command_reasons"][0]["catalog_command_id"],
            "sample_disable",
        )

    def test_policy_no_action_and_missing_finding_emit_no_action_rows(self) -> None:
        report = report_with_findings(
            finding("sat-1", SatelliteOutcome.PAYLOAD_NOISE),
            finding("sat-2", SatelliteOutcome.INCREASED_DRAG),
        )

        rows = generate_command_runbooks_for_report(
            report,
            active_satellites(),
            report_id="report-row-1",
        )
        policy_no_action = self._row_for_satellite(rows, "sat-2")
        no_finding = self._row_for_satellite(rows, "sat-3")

        self.assertEqual(policy_no_action["status"], "no_action")
        self.assertEqual(policy_no_action["commands"], [])
        self.assertEqual(policy_no_action["risk_level"], "medium")
        self.assertTrue(policy_no_action["metadata"]["human_review_required"])
        self.assertIn(
            "no catalogued NOS3 maneuver",
            policy_no_action["metadata"]["no_action_reason"],
        )

        self.assertEqual(no_finding["status"], "no_action")
        self.assertEqual(no_finding["commands"], [])
        self.assertEqual(no_finding["risk_level"], "none")
        self.assertFalse(no_finding["metadata"]["human_review_required"])
        self.assertEqual(no_finding["metadata"]["no_action_reason"], NO_FINDING_REASON)
        self.assertEqual(no_finding["metadata"]["findings"], [])

    def test_batch_helper_generates_every_report_satellite_pair(self) -> None:
        reports = [
            report_with_findings(
                finding("sat-1", SatelliteOutcome.PAYLOAD_NOISE),
                event_window_id="ew-1",
                evidence_hash="hash-1",
            ),
            report_with_findings(
                finding(
                    "sat-2",
                    SatelliteOutcome.STAR_TRACKER_DEGRADED,
                    event_window_id="ew-2",
                ),
                event_window_id="ew-2",
                evidence_hash="hash-2",
            ),
        ]

        rows = generate_command_runbooks_for_reports(
            reports,
            active_satellites(),
            report_ids={"ew-1": "report-row-1", "ew-2": "report-row-2"},
        )

        self.assertEqual(len(rows), 6)
        self.assertEqual(
            {
                (row["report_id"], row["satellite_external_id"])
                for row in rows
            },
            {
                ("report-row-1", "sat-1"),
                ("report-row-1", "sat-2"),
                ("report-row-1", "sat-3"),
                ("report-row-2", "sat-1"),
                ("report-row-2", "sat-2"),
                ("report-row-2", "sat-3"),
            },
        )
        self.assertEqual(len({row["dedupe_key"] for row in rows}), 6)

    def test_accepts_satellite_evidence_inputs_without_database_id(self) -> None:
        report = report_with_findings(
            finding("sat-1", SatelliteOutcome.PAYLOAD_NOISE),
        )
        satellite = SatelliteEvidence(
            external_id="sat-1",
            name="PayloadSat",
            orbit_regime="LEO",
            operational_status="active",
        )

        rows = generate_command_runbooks_for_report(
            report,
            [satellite],
            report_id="report-row-1",
            satellite_metadata={"sat-1": {"supports_sample_payload": True}},
        )

        self.assertEqual(len(rows), 1)
        self.assertNotIn("satellite_id", rows[0])
        self.assertEqual(rows[0]["satellite_external_id"], "sat-1")
        self.assertEqual(rows[0]["commands"][0]["catalog_command_id"], "sample_disable")

    def test_partial_policy_context_map_defaults_for_unmentioned_satellites(self) -> None:
        report = report_with_findings(
            finding("sat-1", SatelliteOutcome.COMMUNICATION_DEGRADED),
            finding("sat-2", SatelliteOutcome.INCREASED_DRAG),
        )

        rows = generate_command_runbooks_for_report(
            report,
            active_satellites(),
            report_id="report-row-1",
            policy_context={"sat-1": {"telemetry_recovery": True}},
        )

        recovered = self._row_for_satellite(rows, "sat-1")
        manual_review = self._row_for_satellite(rows, "sat-2")
        self.assertEqual(
            [command["catalog_command_id"] for command in recovered["commands"]],
            ["radio_resume_output"],
        )
        self.assertEqual(manual_review["status"], "no_action")

    def _row_for_satellite(
        self,
        rows: list[dict[str, object]],
        satellite_external_id: str,
    ) -> dict[str, object]:
        for row in rows:
            if row["satellite_external_id"] == satellite_external_id:
                return row
        raise AssertionError(f"missing row for {satellite_external_id}")


if __name__ == "__main__":
    unittest.main()
