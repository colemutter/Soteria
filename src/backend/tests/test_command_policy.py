from __future__ import annotations

import copy
import unittest

from agent.command_catalog import CommandCatalog, load_command_catalog
from agent.command_policy import (
    POLICY_VERSION,
    CommandPolicyContext,
    CommandPolicyRiskLevel,
    recommend_command_policy_for_finding,
    recommend_command_policy_for_report,
    validate_policy_catalog_command,
)
from agent.report_models import (
    EventWindowSatelliteReport,
    ReportSeverity,
    SatelliteImpactFinding,
    SatelliteOutcome,
)


def finding(
    *outcomes: SatelliteOutcome,
    severity: ReportSeverity = ReportSeverity.MAJOR,
    rationale: str = "Solar weather may affect the satellite subsystem.",
) -> SatelliteImpactFinding:
    return SatelliteImpactFinding(
        satellite_id="sat-1",
        severity=severity,
        possible_outcomes=list(outcomes),
        rationale=rationale,
        source_event_window_ids=["ew-1"],
        source_satellite_ids=["sat-1"],
    )


def report_with_finding(
    satellite_finding: SatelliteImpactFinding,
) -> EventWindowSatelliteReport:
    return EventWindowSatelliteReport(
        event_window_id="ew-1",
        evidence_hash="hash-1",
        event_severity=ReportSeverity.MAJOR,
        summary="Solar weather report.",
        possible_outcomes=satellite_finding.possible_outcomes,
        findings=[satellite_finding],
        confidence="medium",
    )


class CommandPolicyTest(unittest.TestCase):
    def test_payload_protect_selects_sample_disable(self) -> None:
        decision = recommend_command_policy_for_finding(
            finding(SatelliteOutcome.PAYLOAD_NOISE),
            satellite_metadata={"supports_sample_payload": True},
        )

        self.assertEqual(decision.policy_version, POLICY_VERSION)
        self.assertEqual(
            [selection.catalog_command_id for selection in decision.selected_commands],
            ["sample_disable"],
        )
        self.assertFalse(decision.human_review_required)
        self.assertEqual(decision.risk_level, CommandPolicyRiskLevel.LOW)
        self.assertIsNone(decision.no_action_reason)

    def test_payload_protect_without_supported_profile_is_no_action(self) -> None:
        decision = recommend_command_policy_for_finding(
            finding(SatelliteOutcome.PAYLOAD_NOISE),
            satellite_metadata={"supports_sample_payload": False},
        )

        self.assertEqual(decision.selected_commands, [])
        self.assertTrue(decision.human_review_required)
        self.assertIn("does not declare sample payload support", decision.no_action_reason)

    def test_payload_enable_requires_explicit_recovery_setup(self) -> None:
        storm_onset = recommend_command_policy_for_finding(
            finding(SatelliteOutcome.PAYLOAD_NOISE),
            satellite_metadata={"supports_sample_payload": True},
        )
        recovery_setup = recommend_command_policy_for_finding(
            finding(SatelliteOutcome.NO_MATERIAL_SATELLITE_EFFECT_EXPECTED),
            satellite_metadata={"supports_sample_payload": True},
            context=CommandPolicyContext(payload_recovery_setup=True),
        )

        self.assertNotIn(
            "sample_enable",
            [selection.catalog_command_id for selection in storm_onset.selected_commands],
        )
        self.assertEqual(
            [selection.catalog_command_id for selection in recovery_setup.selected_commands],
            ["sample_enable"],
        )

    def test_communication_recovery_selects_radio_resume(self) -> None:
        decision = recommend_command_policy_for_finding(
            finding(SatelliteOutcome.COMMUNICATION_DEGRADED),
            context=CommandPolicyContext(telemetry_recovery=True),
        )

        self.assertEqual(
            [selection.catalog_command_id for selection in decision.selected_commands],
            ["radio_resume_output"],
        )
        self.assertFalse(decision.human_review_required)
        self.assertEqual(decision.risk_level, CommandPolicyRiskLevel.LOW)

    def test_radio_quiet_selects_disable_with_human_review(self) -> None:
        decision = recommend_command_policy_for_finding(
            finding(SatelliteOutcome.COMMUNICATION_DEGRADED),
            context=CommandPolicyContext(communications_quiet_posture=True),
        )

        self.assertEqual(
            [selection.catalog_command_id for selection in decision.selected_commands],
            ["radio_disable_output"],
        )
        self.assertTrue(decision.human_review_required)
        self.assertEqual(decision.risk_level, CommandPolicyRiskLevel.MEDIUM)

    def test_adcs_degradation_selects_sunsafe(self) -> None:
        decision = recommend_command_policy_for_finding(
            finding(SatelliteOutcome.STAR_TRACKER_DEGRADED),
        )

        self.assertEqual(
            [selection.catalog_command_id for selection in decision.selected_commands],
            ["adcs_set_sunsafe"],
        )
        self.assertTrue(decision.human_review_required)
        self.assertEqual(decision.risk_level, CommandPolicyRiskLevel.HIGH)

    def test_orbit_drag_selects_commandability_check(self) -> None:
        decision = recommend_command_policy_for_finding(
            finding(SatelliteOutcome.INCREASED_DRAG),
        )

        self.assertEqual(
            [selection.catalog_command_id for selection in decision.selected_commands],
            ["cfs_noop"],
        )
        self.assertFalse(decision.human_review_required)
        self.assertEqual(decision.risk_level, CommandPolicyRiskLevel.LOW)
        self.assertIn(
            "commandability check",
            decision.selected_commands[0].reason,
        )
        self.assertIsNone(decision.no_action_reason)

    def test_geomagnetic_pointing_and_tracking_selects_sunsafe_and_noop(self) -> None:
        decision = recommend_command_policy_for_finding(
            finding(
                SatelliteOutcome.ADCS_DISTURBANCE,
                SatelliteOutcome.TRACKING_UNCERTAINTY,
            ),
        )

        self.assertEqual(
            [selection.catalog_command_id for selection in decision.selected_commands],
            ["adcs_set_sunsafe", "cfs_noop"],
        )
        self.assertTrue(decision.human_review_required)
        self.assertEqual(decision.risk_level, CommandPolicyRiskLevel.HIGH)

    def test_generic_radiation_protection_is_no_action(self) -> None:
        decision = recommend_command_policy_for_finding(
            finding(SatelliteOutcome.SINGLE_EVENT_EFFECTS),
        )

        self.assertEqual(decision.selected_commands, [])
        self.assertTrue(decision.human_review_required)
        self.assertIn("Generic radiation", decision.no_action_reason)

    def test_generic_eps_load_shed_is_no_action(self) -> None:
        decision = recommend_command_policy_for_finding(
            finding(SatelliteOutcome.SOLAR_ARRAY_DEGRADATION),
            context=CommandPolicyContext(explicit_eps_load_shed=True),
        )

        self.assertEqual(decision.selected_commands, [])
        self.assertTrue(decision.human_review_required)
        self.assertIn("Generic EPS load shedding remains unresolved", decision.no_action_reason)

    def test_unresolved_catalog_commands_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unresolved catalog command"):
            validate_policy_catalog_command("radiation_protect_generic")

        with self.assertRaisesRegex(ValueError, "unresolved catalog command"):
            validate_policy_catalog_command("eps_load_shed_policy")

    def test_missing_catalog_command_cannot_be_selected(self) -> None:
        payload = load_command_catalog().model_dump(mode="json")
        payload["commands"] = [
            command
            for command in payload["commands"]
            if command["id"] != "sample_disable"
        ]
        catalog_without_sample_disable = CommandCatalog.model_validate(
            copy.deepcopy(payload)
        )

        with self.assertRaisesRegex(ValueError, "unknown catalog command ID"):
            recommend_command_policy_for_finding(
                finding(SatelliteOutcome.PAYLOAD_NOISE),
                satellite_metadata={"supports_sample_payload": True},
                catalog=catalog_without_sample_disable,
            )

    def test_report_level_outcomes_do_not_leak_into_finding_decision(self) -> None:
        satellite_finding = finding(SatelliteOutcome.COMMUNICATION_DEGRADED)
        report = EventWindowSatelliteReport(
            event_window_id="ew-1",
            evidence_hash="hash-1",
            event_severity=ReportSeverity.MAJOR,
            summary="Solar weather report.",
            possible_outcomes=[
                SatelliteOutcome.COMMUNICATION_DEGRADED,
                SatelliteOutcome.INCREASED_DRAG,
            ],
            findings=[satellite_finding],
            confidence="medium",
        )

        decision = recommend_command_policy_for_finding(
            satellite_finding,
            report=report,
            context=CommandPolicyContext(telemetry_recovery=True),
        )

        self.assertEqual(
            [selection.catalog_command_id for selection in decision.selected_commands],
            ["radio_resume_output"],
        )

    def test_report_input_returns_decision_per_finding(self) -> None:
        satellite_finding = finding(SatelliteOutcome.PAYLOAD_NOISE)
        report = report_with_finding(satellite_finding)

        result = recommend_command_policy_for_report(
            report,
            satellite_metadata={"sat-1": {"supports_sample_payload": True}},
        )

        self.assertEqual(result.policy_version, POLICY_VERSION)
        self.assertEqual(result.event_window_id, "ew-1")
        self.assertEqual(len(result.decisions), 1)
        self.assertEqual(
            [
                selection.catalog_command_id
                for selection in result.decisions[0].selected_commands
            ],
            ["sample_disable"],
        )


if __name__ == "__main__":
    unittest.main()
