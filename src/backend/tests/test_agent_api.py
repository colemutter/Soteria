from __future__ import annotations

import unittest
from types import SimpleNamespace

from fastapi.testclient import TestClient

from api import agent as agent_api
from agent.report_generation import EventWindowReportRunResult
from agent.report_models import (
    EventWindowSatelliteReport,
    ReportSeverity,
    SatelliteImpactFinding,
    SatelliteOutcome,
)
from main import app


class AgentApiTest(unittest.TestCase):
    def test_reaction_endpoint_accepts_event_window_payload(self) -> None:
        original_runner = agent_api.run_reaction_agent

        async def noop_reaction_agent(reaction, session_id):
            return None

        agent_api.run_reaction_agent = noop_reaction_agent
        try:
            response = TestClient(app).post(
                "/agent/reactions",
                json={
                    "event_window_id": "ew_123",
                    "event_key": "xray:2026-06-21T00:00:00Z",
                    "event_type": "xray_flux",
                    "source_product": "swpc_goes_xray",
                    "status": "active",
                    "confidence": "high",
                    "priority": "normal",
                    "peak_severity": 2,
                    "window_start": "2026-06-21T00:00:00Z",
                    "window_end": "2026-06-21T01:00:00Z",
                    "updated_at": "2026-06-21T00:05:00Z",
                    "detected_at": "2026-06-21T00:05:01Z",
                },
            )
        finally:
            agent_api.run_reaction_agent = original_runner

        self.assertEqual(response.status_code, 202)
        self.assertEqual(
            response.json(),
            {
                "status": "accepted",
                "agent_name": "event-report-agent",
                "event_window_id": "ew_123",
                "priority": "normal",
                "session_id": "event-window:ew_123",
            },
        )

    def test_poller_report_endpoint_accepts_batch_payload(self) -> None:
        original_get_client = agent_api._get_supabase_client
        original_generator = agent_api.generate_reports_for_event_windows
        original_persist = agent_api.persist_report_run_result
        calls = []
        persist_calls = []

        async def fake_generate_reports(event_window_ids, *, client, session_id):
            calls.append(
                {
                    "event_window_ids": event_window_ids,
                    "client": client,
                    "session_id": session_id,
                }
            )
            return EventWindowReportRunResult(
                status="completed",
                requested_event_window_ids=event_window_ids,
                resolved_event_window_ids=event_window_ids,
                missing_event_window_ids=[],
                reports=[],
                failures=[],
                validation_errors=[],
                session_id=session_id,
            )

        sentinel_client = object()
        agent_api._get_supabase_client = lambda: sentinel_client
        agent_api.generate_reports_for_event_windows = fake_generate_reports
        agent_api.persist_report_run_result = lambda client, result: persist_calls.append(
            (client, result)
        ) or 1
        try:
            response = TestClient(app).post(
                "/api/poller/report",
                json={
                    "trigger_type": "event_windows_changed",
                    "trigger_source": "space_weather_event_windows",
                    "priority": "high",
                    "event_window_ids": ["ew_123", "ew_456"],
                    "event_windows": [
                        {
                            "event_window_id": "ew_123",
                            "event_key": "xray:2026-06-21T00:00:00Z",
                            "event_type": "xray_flux",
                            "source_product": "swpc_goes_xray",
                            "status": "active",
                            "confidence": "high",
                            "priority": "normal",
                            "peak_severity": 2,
                            "window_start": "2026-06-21T00:00:00Z",
                            "window_end": "2026-06-21T01:00:00Z",
                            "updated_at": "2026-06-21T00:05:00Z",
                            "detected_at": "2026-06-21T00:05:01Z",
                        },
                        {
                            "event_window_id": "ew_456",
                            "event_key": "kp:2026-06-21T00:00:00Z",
                            "event_type": "geomagnetic_storm_risk",
                            "source_product": "swpc_kp_forecast",
                            "status": "active",
                            "confidence": "medium",
                            "priority": "high",
                            "peak_severity": 4,
                            "window_start": "2026-06-21T00:00:00Z",
                            "window_end": "2026-06-21T03:00:00Z",
                            "updated_at": "2026-06-21T00:05:00Z",
                            "detected_at": "2026-06-21T00:05:01Z",
                        },
                    ],
                    "detected_at": "2026-06-21T00:05:02Z",
                },
            )
        finally:
            agent_api._get_supabase_client = original_get_client
            agent_api.generate_reports_for_event_windows = original_generator
            agent_api.persist_report_run_result = original_persist

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "completed")
        self.assertEqual(response.json()["persisted_rows_count"], 1)
        self.assertEqual(calls[0]["event_window_ids"], ["ew_123", "ew_456"])
        self.assertIs(calls[0]["client"], sentinel_client)
        self.assertTrue(calls[0]["session_id"].startswith("poller:"))
        self.assertIs(persist_calls[0][0], sentinel_client)

    def test_poller_report_endpoint_generates_runbooks_for_active_satellites(self) -> None:
        original_get_client = agent_api._get_supabase_client
        original_generator = agent_api.generate_reports_for_event_windows
        original_persist_reports = agent_api.persist_report_run_result
        original_query_satellites = agent_api.query_active_satellite_evidence
        original_generate_runbooks = agent_api.generate_command_runbooks_for_reports
        original_persist_runbooks = agent_api.persist_command_runbook_rows
        calls = {
            "reports": [],
            "satellites": [],
            "runbooks": [],
            "persisted_runbooks": [],
        }
        report = EventWindowSatelliteReport(
            event_window_id="ew_123",
            evidence_hash="hash_123",
            event_severity=ReportSeverity.MAJOR,
            summary="Radiation may affect sample payload data quality.",
            possible_outcomes=[SatelliteOutcome.PAYLOAD_NOISE],
            findings=[
                SatelliteImpactFinding(
                    satellite_id="sat-1",
                    severity=ReportSeverity.MAJOR,
                    possible_outcomes=[SatelliteOutcome.PAYLOAD_NOISE],
                    rationale="Payload data quality may degrade.",
                    source_event_window_ids=["ew_123"],
                    source_satellite_ids=["sat-1"],
                )
            ],
            confidence="medium",
        )

        async def fake_generate_reports(event_window_ids, *, client, session_id):
            calls["reports"].append(
                {
                    "event_window_ids": event_window_ids,
                    "client": client,
                    "session_id": session_id,
                }
            )
            return EventWindowReportRunResult(
                status="completed",
                requested_event_window_ids=event_window_ids,
                resolved_event_window_ids=event_window_ids,
                missing_event_window_ids=[],
                reports=[report],
                failures=[],
                validation_errors=[],
                session_id=session_id,
            )

        def fake_query_active_satellites(client):
            calls["satellites"].append(client)
            return SimpleNamespace(
                satellites=[
                    {"external_id": "sat-1", "name": "PayloadSat"},
                    {"external_id": "sat-2", "name": "QuietSat"},
                    {"external_id": "sat-3", "name": "DragSat"},
                ],
                validation_errors=[],
            )

        def fake_generate_runbooks(reports, satellites):
            calls["runbooks"].append((reports, satellites))
            return [
                {"dedupe_key": "runbook:report:sat-1"},
                {"dedupe_key": "runbook:report:sat-2"},
                {"dedupe_key": "runbook:report:sat-3"},
            ]

        def fake_persist_runbooks(client, rows):
            calls["persisted_runbooks"].append((client, rows))
            return len(rows)

        sentinel_client = object()
        agent_api._get_supabase_client = lambda: sentinel_client
        agent_api.generate_reports_for_event_windows = fake_generate_reports
        agent_api.persist_report_run_result = lambda client, result: 1
        agent_api.query_active_satellite_evidence = fake_query_active_satellites
        agent_api.generate_command_runbooks_for_reports = fake_generate_runbooks
        agent_api.persist_command_runbook_rows = fake_persist_runbooks
        try:
            response = TestClient(app).post(
                "/api/poller/report",
                json={
                    "trigger_type": "event_windows_changed",
                    "trigger_source": "space_weather_event_windows",
                    "priority": "high",
                    "event_window_ids": ["ew_123"],
                    "event_windows": [
                        {
                            "event_window_id": "ew_123",
                            "event_key": "proton:2026-06-21T00:00:00Z",
                            "event_type": "proton_flux",
                            "source_product": "swpc_proton_flux",
                            "status": "active",
                            "confidence": "high",
                            "priority": "high",
                            "peak_severity": 3,
                            "window_start": "2026-06-21T00:00:00Z",
                            "window_end": "2026-06-21T01:00:00Z",
                            "updated_at": "2026-06-21T00:05:00Z",
                            "detected_at": "2026-06-21T00:05:01Z",
                        }
                    ],
                    "detected_at": "2026-06-21T00:05:02Z",
                },
            )
        finally:
            agent_api._get_supabase_client = original_get_client
            agent_api.generate_reports_for_event_windows = original_generator
            agent_api.persist_report_run_result = original_persist_reports
            agent_api.query_active_satellite_evidence = original_query_satellites
            agent_api.generate_command_runbooks_for_reports = original_generate_runbooks
            agent_api.persist_command_runbook_rows = original_persist_runbooks

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["runbooks_generated_count"], 3)
        self.assertEqual(response.json()["runbooks_persisted_count"], 3)
        self.assertEqual(response.json()["runbook_errors"], [])
        self.assertIs(calls["satellites"][0], sentinel_client)
        reports, satellites = calls["runbooks"][0]
        self.assertEqual(reports, [report])
        self.assertEqual(len(satellites), 3)
        persisted_client, persisted_rows = calls["persisted_runbooks"][0]
        self.assertIs(persisted_client, sentinel_client)
        self.assertEqual(len(persisted_rows), 3)

    def test_poller_report_endpoint_marks_demo_pipeline_rows(self) -> None:
        original_get_client = agent_api._get_supabase_client
        original_generator = agent_api.generate_reports_for_event_windows
        original_persist_reports = agent_api.persist_report_run_result
        original_query_satellites = agent_api.query_active_satellite_evidence
        original_generate_runbooks = agent_api.generate_command_runbooks_for_reports
        original_persist_runbooks = agent_api.persist_command_runbook_rows
        calls = {
            "persist_report_kwargs": [],
            "runbook_kwargs": [],
        }
        report = EventWindowSatelliteReport(
            event_window_id="ew_demo",
            evidence_hash="hash_demo",
            event_severity=ReportSeverity.MAJOR,
            summary="Demo geomagnetic storm may affect payload data quality.",
            possible_outcomes=[SatelliteOutcome.PAYLOAD_NOISE],
            findings=[
                SatelliteImpactFinding(
                    satellite_id="sat-1",
                    severity=ReportSeverity.MAJOR,
                    possible_outcomes=[SatelliteOutcome.PAYLOAD_NOISE],
                    rationale="Payload data quality may degrade.",
                    source_event_window_ids=["ew_demo"],
                    source_satellite_ids=["sat-1"],
                )
            ],
            confidence="medium",
        )

        async def fake_generate_reports(event_window_ids, *, client, session_id):
            return EventWindowReportRunResult(
                status="completed",
                requested_event_window_ids=event_window_ids,
                resolved_event_window_ids=event_window_ids,
                missing_event_window_ids=[],
                reports=[report],
                failures=[],
                validation_errors=[],
                session_id=session_id,
            )

        def fake_persist_reports(client, result, **kwargs):
            calls["persist_report_kwargs"].append(kwargs)
            return 1

        def fake_generate_runbooks(reports, satellites, **kwargs):
            calls["runbook_kwargs"].append(kwargs)
            return [{"dedupe_key": "runbook:demo:sat-1", "demo": True}]

        sentinel_client = object()
        agent_api._get_supabase_client = lambda: sentinel_client
        agent_api.generate_reports_for_event_windows = fake_generate_reports
        agent_api.persist_report_run_result = fake_persist_reports
        agent_api.query_active_satellite_evidence = lambda client: SimpleNamespace(
            satellites=[{"external_id": "sat-1", "name": "DemoSat"}],
            validation_errors=[],
        )
        agent_api.generate_command_runbooks_for_reports = fake_generate_runbooks
        agent_api.persist_command_runbook_rows = lambda client, rows: len(rows)
        try:
            response = TestClient(app).post(
                "/api/poller/report",
                json={
                    "trigger_type": "event_windows_changed",
                    "trigger_source": "space_weather_event_windows",
                    "priority": "high",
                    "event_window_ids": ["ew_demo"],
                    "event_windows": [
                        {
                            "event_window_id": "ew_demo",
                            "event_key": "kp:2026-06-21T00:00:00Z",
                            "event_type": "geomagnetic_storm_risk",
                            "source_product": "local_test_fake_event",
                            "status": "active",
                            "confidence": "forecast",
                            "priority": "high",
                            "demo": True,
                            "peak_severity": 4,
                            "window_start": "2026-06-21T00:00:00Z",
                            "window_end": "2026-06-21T02:00:00Z",
                            "updated_at": "2026-06-21T00:05:00Z",
                            "detected_at": "2026-06-21T00:05:01Z",
                        }
                    ],
                    "detected_at": "2026-06-21T00:05:02Z",
                },
            )
        finally:
            agent_api._get_supabase_client = original_get_client
            agent_api.generate_reports_for_event_windows = original_generator
            agent_api.persist_report_run_result = original_persist_reports
            agent_api.query_active_satellite_evidence = original_query_satellites
            agent_api.generate_command_runbooks_for_reports = original_generate_runbooks
            agent_api.persist_command_runbook_rows = original_persist_runbooks

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            calls["persist_report_kwargs"][0]["demo_event_window_ids"],
            {"ew_demo"},
        )
        self.assertEqual(
            calls["runbook_kwargs"][0]["demo_event_window_ids"],
            {"ew_demo"},
        )

    def test_poller_report_endpoint_returns_error_when_runbook_generation_fails(
        self,
    ) -> None:
        original_get_client = agent_api._get_supabase_client
        original_generator = agent_api.generate_reports_for_event_windows
        original_persist_reports = agent_api.persist_report_run_result
        original_query_satellites = agent_api.query_active_satellite_evidence
        original_generate_runbooks = agent_api.generate_command_runbooks_for_reports
        report = EventWindowSatelliteReport(
            event_window_id="ew_123",
            evidence_hash="hash_123",
            event_severity=ReportSeverity.MAJOR,
            summary="ADCS may need protective posture.",
            possible_outcomes=[SatelliteOutcome.ADCS_DISTURBANCE],
            findings=[
                SatelliteImpactFinding(
                    satellite_id="sat-1",
                    severity=ReportSeverity.MAJOR,
                    possible_outcomes=[SatelliteOutcome.ADCS_DISTURBANCE],
                    rationale="Pointing stability may degrade.",
                    source_event_window_ids=["ew_123"],
                    source_satellite_ids=["sat-1"],
                )
            ],
            confidence="medium",
        )

        async def fake_generate_reports(event_window_ids, *, client, session_id):
            return EventWindowReportRunResult(
                status="completed",
                requested_event_window_ids=event_window_ids,
                resolved_event_window_ids=event_window_ids,
                missing_event_window_ids=[],
                reports=[report],
                failures=[],
                validation_errors=[],
                session_id=session_id,
            )

        def fail_generate_runbooks(reports, satellites):
            raise RuntimeError("catalog file missing")

        sentinel_client = object()
        agent_api._get_supabase_client = lambda: sentinel_client
        agent_api.generate_reports_for_event_windows = fake_generate_reports
        agent_api.persist_report_run_result = lambda client, result: 1
        agent_api.query_active_satellite_evidence = lambda client: SimpleNamespace(
            satellites=[{"external_id": "sat-1", "name": "AdcsSat"}],
            validation_errors=[],
        )
        agent_api.generate_command_runbooks_for_reports = fail_generate_runbooks
        try:
            response = TestClient(app).post(
                "/api/poller/report",
                json={
                    "trigger_type": "event_windows_changed",
                    "trigger_source": "space_weather_event_windows",
                    "priority": "high",
                    "event_window_ids": ["ew_123"],
                    "event_windows": [
                        {
                            "event_window_id": "ew_123",
                            "event_key": "kp:2026-06-21T00:00:00Z",
                            "event_type": "geomagnetic_storm_risk",
                            "source_product": "swpc_kp_forecast",
                            "status": "active",
                            "confidence": "high",
                            "priority": "high",
                            "peak_severity": 3,
                            "window_start": "2026-06-21T00:00:00Z",
                            "window_end": "2026-06-21T01:00:00Z",
                            "updated_at": "2026-06-21T00:05:00Z",
                            "detected_at": "2026-06-21T00:05:01Z",
                        }
                    ],
                    "detected_at": "2026-06-21T00:05:02Z",
                },
            )
        finally:
            agent_api._get_supabase_client = original_get_client
            agent_api.generate_reports_for_event_windows = original_generator
            agent_api.persist_report_run_result = original_persist_reports
            agent_api.query_active_satellite_evidence = original_query_satellites
            agent_api.generate_command_runbooks_for_reports = original_generate_runbooks

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["status"], "completed")
        self.assertEqual(response.json()["persisted_rows_count"], 1)
        self.assertEqual(response.json()["runbooks_generated_count"], 0)
        self.assertIn("catalog file missing", response.json()["runbook_errors"])


if __name__ == "__main__":
    unittest.main()
