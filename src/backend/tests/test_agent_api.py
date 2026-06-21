from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from api import agent as agent_api
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


if __name__ == "__main__":
    unittest.main()
