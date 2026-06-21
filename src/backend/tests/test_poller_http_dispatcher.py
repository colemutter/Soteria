from __future__ import annotations

import datetime as dt
import json
import unittest

from api import poller as poller_api
from api.poller import (
    EventWindowReactionBatch,
    EventWindowReactionMessage,
    HttpReactionDispatcher,
)


class FakeHttpResponse:
    def __init__(self, payload: dict, *, status: int = 200) -> None:
        self.payload = payload
        self.status = status

    def __enter__(self) -> FakeHttpResponse:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class HttpReactionDispatcherTest(unittest.TestCase):
    def test_dispatcher_logs_response_summary(self) -> None:
        original_urlopen = poller_api.urlopen
        captured = {}

        def fake_urlopen(request, timeout):
            captured["request_body"] = request.data
            captured["timeout"] = timeout
            return FakeHttpResponse(
                {
                    "status": "completed",
                    "requested_event_window_ids": ["ew_123"],
                    "reports": [{"event_window_id": "ew_123"}],
                    "failures": [],
                    "persisted_rows_count": 1,
                    "persistence_errors": [],
                    "runbooks_generated_count": 3,
                    "runbooks_persisted_count": 3,
                    "runbook_errors": [],
                    "validation_errors": [],
                }
            )

        poller_api.urlopen = fake_urlopen
        try:
            dispatcher = HttpReactionDispatcher(
                "http://example.test/api/poller/report",
                timeout_seconds=123,
            )
            with self.assertLogs("soteria.poller", level="INFO") as logs:
                dispatcher._post(reaction_batch())
        finally:
            poller_api.urlopen = original_urlopen

        self.assertEqual(captured["timeout"], 123)
        self.assertIn(b'"event_window_ids":["ew_123"]', captured["request_body"])
        log_output = "\n".join(logs.output)
        self.assertIn("runbooks_generated=3", log_output)
        self.assertIn("runbooks_persisted=3", log_output)
        self.assertIn("event_window_ids=['ew_123']", log_output)

    def test_dispatcher_raises_when_response_contains_runbook_errors(self) -> None:
        original_urlopen = poller_api.urlopen

        def fake_urlopen(request, timeout):
            return FakeHttpResponse(
                {
                    "status": "completed",
                    "requested_event_window_ids": ["ew_123"],
                    "reports": [{"event_window_id": "ew_123"}],
                    "failures": [],
                    "persisted_rows_count": 1,
                    "persistence_errors": [],
                    "runbooks_generated_count": 3,
                    "runbooks_persisted_count": 0,
                    "runbook_errors": ["catalog file missing"],
                    "validation_errors": [],
                }
            )

        poller_api.urlopen = fake_urlopen
        try:
            dispatcher = HttpReactionDispatcher("http://example.test/api/poller/report")
            with self.assertLogs("soteria.poller", level="ERROR") as logs:
                with self.assertRaisesRegex(RuntimeError, "catalog file missing"):
                    dispatcher._post(reaction_batch())
        finally:
            poller_api.urlopen = original_urlopen

        log_output = "\n".join(logs.output)
        self.assertIn("runbooks_generated=3", log_output)
        self.assertIn("runbooks_persisted=0", log_output)
        self.assertIn("catalog file missing", log_output)


def reaction_batch() -> EventWindowReactionBatch:
    now = dt.datetime(2026, 6, 21, 8, 35, tzinfo=dt.UTC)
    return EventWindowReactionBatch(
        priority="high",
        event_window_ids=["ew_123"],
        event_windows=[
            EventWindowReactionMessage(
                event_window_id="ew_123",
                event_key="a" * 64,
                event_type="geomagnetic_storm_risk",
                source_product="soteria_test",
                status="active",
                confidence="forecast",
                priority="high",
                peak_severity=3,
                window_start=now - dt.timedelta(minutes=5),
                window_end=now + dt.timedelta(hours=2),
                updated_at=now,
                detected_at=now,
            )
        ],
        detected_at=now,
    )


if __name__ == "__main__":
    unittest.main()
