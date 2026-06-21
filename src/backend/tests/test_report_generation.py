from __future__ import annotations

import asyncio
import datetime as dt
import unittest
from typing import Any

from claude_agent_sdk import ResultMessage

from agent import report_generation
from agent.report_generation import build_report_prompt, generate_report_from_bundle
from agent.report_generation import persist_report_run_result
from agent.report_models import EventWindowEvidence, ReportEvidenceBundle, SatelliteEvidence


NOW = dt.datetime(2026, 6, 21, 12, 0, tzinfo=dt.UTC)


def bundle() -> ReportEvidenceBundle:
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
        ),
        satellites=[
            SatelliteEvidence(
                external_id="real-25544",
                name="ISS (ZARYA)",
                orbit_regime="LEO",
                operational_status="active",
            )
        ],
        evidence_hash="hash_123",
        created_at=NOW,
    )


def structured_report(**overrides: Any) -> dict[str, Any]:
    payload = {
        "event_window_id": "ew_123",
        "evidence_hash": "hash_123",
        "event_severity": "major",
        "summary": "Geomagnetic activity may increase LEO drag.",
        "possible_outcomes": ["increased_drag"],
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
    payload.update(overrides)
    return payload


def result_message(structured_output: Any, *, is_error: bool = False) -> ResultMessage:
    return ResultMessage(
        subtype="success" if not is_error else "error",
        duration_ms=1,
        duration_api_ms=1,
        is_error=is_error,
        num_turns=1,
        session_id="session_123",
        result=None,
        structured_output=structured_output,
        errors=["agent failed"] if is_error else None,
    )


class FakeClient:
    def __init__(self, messages: list[ResultMessage]) -> None:
        self.messages = messages
        self.prompts: list[str] = []

    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def query(self, prompt: str) -> None:
        self.prompts.append(prompt)

    async def receive_response(self):
        for message in self.messages:
            yield message


class FakeSupabaseQuery:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        self.on_conflict: str | None = None

    def upsert(self, rows: list[dict[str, Any]], on_conflict: str):
        self.rows = rows
        self.on_conflict = on_conflict
        return self

    def execute(self):
        return type("Response", (), {"data": self.rows})()


class FakeSupabaseClient:
    def __init__(self) -> None:
        self.query = FakeSupabaseQuery()

    def table(self, name: str) -> FakeSupabaseQuery:
        self.table_name = name
        return self.query


class ReportGenerationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.original_create_agent_client = report_generation.create_agent_client
        self.created_clients: list[FakeClient] = []
        self.create_kwargs: list[dict[str, Any]] = []

    def tearDown(self) -> None:
        report_generation.create_agent_client = self.original_create_agent_client

    def patch_client(self, messages: list[ResultMessage]) -> None:
        def fake_create_agent_client(**kwargs):
            self.create_kwargs.append(kwargs)
            client = FakeClient(messages)
            self.created_clients.append(client)
            return client

        report_generation.create_agent_client = fake_create_agent_client

    def test_prompt_lists_allowed_values_and_avoids_tool_fetching(self) -> None:
        prompt = build_report_prompt(bundle())

        self.assertIn("Allowed severity values: none, minor, moderate", prompt)
        self.assertIn("increased_drag", prompt)
        self.assertIn("ew_123", prompt)
        self.assertIn("real-25544", prompt)
        self.assertIn("relevance-filtered", prompt)
        self.assertIn("impact_guidance", prompt)
        self.assertNotIn("Use get_event_windows", prompt)
        self.assertNotIn("Use get_user_satellites", prompt)

    def test_structured_output_generates_valid_report(self) -> None:
        self.patch_client([result_message(structured_report())])

        result = asyncio.run(generate_report_from_bundle(bundle()))

        self.assertTrue(result.ok)
        self.assertEqual(result.report.event_window_id, "ew_123")
        self.assertEqual(self.create_kwargs[0]["allowed_tools"], [])
        self.assertEqual(
            self.create_kwargs[0]["output_format"]["type"],
            "json_schema",
        )

    def test_invented_outcome_becomes_validation_failure(self) -> None:
        self.patch_client(
            [
                result_message(
                    structured_report(possible_outcomes=["mystery_effect"])
                )
            ]
        )

        result = asyncio.run(generate_report_from_bundle(bundle(), max_attempts=1))

        self.assertFalse(result.ok)
        self.assertEqual(result.failure.code, "validation_error")

    def test_missing_structured_output_becomes_typed_failure(self) -> None:
        self.patch_client([result_message(None)])

        result = asyncio.run(generate_report_from_bundle(bundle(), max_attempts=1))

        self.assertFalse(result.ok)
        self.assertEqual(result.failure.code, "missing_structured_output")

    def test_agent_error_becomes_typed_failure(self) -> None:
        self.patch_client([result_message(None, is_error=True)])

        result = asyncio.run(generate_report_from_bundle(bundle()))

        self.assertFalse(result.ok)
        self.assertEqual(result.failure.code, "agent_error")

    def test_persist_report_run_result_upserts_report_rows(self) -> None:
        self.patch_client([result_message(structured_report())])
        result = asyncio.run(generate_report_from_bundle(bundle()))
        run_result = report_generation.EventWindowReportRunResult(
            status="completed",
            requested_event_window_ids=["ew_123"],
            resolved_event_window_ids=["ew_123"],
            missing_event_window_ids=[],
            reports=[result.report],
            failures=[],
            validation_errors=[],
            session_id="session_123",
        )
        client = FakeSupabaseClient()

        count = persist_report_run_result(client, run_result)

        self.assertEqual(count, 1)
        self.assertEqual(client.table_name, "satellite_event_reports")
        self.assertEqual(client.query.on_conflict, "dedupe_key")
        self.assertEqual(client.query.rows[0]["status"], "validated")
        self.assertEqual(
            client.query.rows[0]["dedupe_key"],
            "report:ew_123:hash_123",
        )
        self.assertFalse(client.query.rows[0]["demo"])

    def test_persist_report_run_result_marks_demo_rows(self) -> None:
        self.patch_client([result_message(structured_report())])
        result = asyncio.run(generate_report_from_bundle(bundle()))
        run_result = report_generation.EventWindowReportRunResult(
            status="completed",
            requested_event_window_ids=["ew_123"],
            resolved_event_window_ids=["ew_123"],
            missing_event_window_ids=[],
            reports=[result.report],
            failures=[],
            validation_errors=[],
            session_id="session_123",
        )
        client = FakeSupabaseClient()

        persist_report_run_result(
            client,
            run_result,
            demo_event_window_ids={"ew_123"},
        )

        self.assertTrue(client.query.rows[0]["demo"])


if __name__ == "__main__":
    unittest.main()
