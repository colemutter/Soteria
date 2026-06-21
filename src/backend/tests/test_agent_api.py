from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from api import agent as agent_api
from agent.report_generation import EventWindowReportRunResult
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


if __name__ == "__main__":
    unittest.main()
