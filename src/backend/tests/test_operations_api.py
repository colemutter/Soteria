from __future__ import annotations

import unittest
from typing import Any

from fastapi.testclient import TestClient

from agent.command_catalog import get_catalog_command, load_command_catalog
from api import operations as operations_api
from main import app


class FakeQuery:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data
        self.calls: list[tuple[str, Any]] = []

    def select(self, columns: str):
        self.calls.append(("select", columns))
        return self

    def order(self, column: str):
        self.calls.append(("order", column))
        return self

    def limit(self, value: int):
        self.calls.append(("limit", value))
        return self

    def eq(self, column: str, value: Any):
        self.calls.append(("eq", (column, value)))
        return self

    def upsert(self, rows: Any, on_conflict: str):
        self.calls.append(("upsert", (rows, on_conflict)))
        self.data = rows if isinstance(rows, list) else [{**rows, "id": "runbook_123"}]
        return self

    def insert(self, row: dict[str, Any]):
        self.calls.append(("insert", row))
        self.data = [{**row, "id": "runbook_123"}]
        return self

    def execute(self):
        return type("Response", (), {"data": self.data})()


class FakeClient:
    def __init__(self) -> None:
        self.queries: dict[str, FakeQuery] = {}

    def table(self, name: str) -> FakeQuery:
        query = self.queries.setdefault(name, FakeQuery([]))
        return query


class OperationsApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.original_get_client = operations_api._get_supabase_client
        self.client = FakeClient()
        operations_api._get_supabase_client = lambda: self.client

    def tearDown(self) -> None:
        operations_api._get_supabase_client = self.original_get_client

    def test_create_satellites_upserts_frontend_rows(self) -> None:
        response = TestClient(app).post(
            "/api/satellites",
            json={
                "satellites": [
                    {
                        "external_id": "real-25544",
                        "norad_cat_id": 25544,
                        "name": "ISS (ZARYA)",
                        "orbit_regime": "LEO",
                        "tle_line1": "1 25544U 98067A",
                        "tle_line2": "2 25544 51.6",
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "created")
        self.assertEqual(response.json()["count"], 1)
        self.assertEqual(
            self.client.queries["satellites"].calls[-1][0],
            "upsert",
        )

    def test_get_satellites_applies_filters(self) -> None:
        self.client.queries["satellites"] = FakeQuery(
            [{"external_id": "real-25544", "name": "ISS (ZARYA)"}]
        )

        response = TestClient(app).get(
            "/api/satellites?limit=25&orbit_regime=leo&operational_status=active"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"satellites": [{"external_id": "real-25544", "name": "ISS (ZARYA)"}]},
        )
        self.assertIn(
            ("eq", ("orbit_regime", "LEO")),
            self.client.queries["satellites"].calls,
        )
        self.assertIn(
            ("eq", ("operational_status", "active")),
            self.client.queries["satellites"].calls,
        )

    def catalog_backed_runbook(self, **overrides: Any) -> dict[str, Any]:
        command = get_catalog_command("radio_enable_output")
        payload = {
            "report_id": "report_123",
            "event_window_id": "11111111-1111-1111-1111-111111111111",
            "satellite_external_id": "real-25544",
            "catalog_version": load_command_catalog().catalog_version,
            "policy_version": "solar-weather-command-policy.20260621",
            "evidence_hash": "evidence_hash_123",
            "dedupe_key": "runbook:report_123:real-25544",
            "title": "Monitor ISS drag risk",
            "commands": [
                {
                    "catalog_command_id": command.id,
                    "target": command.target,
                    "command": command.command,
                    "args": [
                        arg.model_dump(mode="json", exclude_none=True)
                        for arg in command.args
                    ],
                    "human_review_required": command.human_review_required,
                    "automated_allowed": command.automated_allowed,
                    "verifier": command.verifier.model_dump(mode="json"),
                    "rendered_script": "cmd('CFS_RADIO TO_ENABLE_OUTPUT')",
                }
            ],
        }
        payload.update(overrides)
        return payload

    def test_receive_generated_runbook_upserts_catalog_backed_status(self) -> None:
        response = TestClient(app).post(
            "/api/runbooks/generated",
            json={"runbook": self.catalog_backed_runbook()},
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "accepted")
        upsert_call = self.client.queries["command_runbooks"].calls[-1]
        self.assertEqual(upsert_call[0], "upsert")
        row, on_conflict = upsert_call[1]
        self.assertEqual(on_conflict, "dedupe_key")
        self.assertEqual(row["status"], "generated")
        self.assertEqual(row["dedupe_key"], "runbook:report_123:real-25544")

    def test_receive_generated_runbook_accepts_no_action_reason(self) -> None:
        response = TestClient(app).post(
            "/api/runbooks/generated",
            json={
                "runbook": self.catalog_backed_runbook(
                    commands=[],
                    status="no_action",
                    metadata={
                        "no_action_reason": "No safe catalog command applies."
                    },
                )
            },
        )

        self.assertEqual(response.status_code, 202)
        upsert_call = self.client.queries["command_runbooks"].calls[-1]
        row, on_conflict = upsert_call[1]
        self.assertEqual(on_conflict, "dedupe_key")
        self.assertEqual(row["status"], "no_action")
        self.assertEqual(row["commands"], [])

    def test_receive_generated_runbook_rejects_unknown_catalog_id(self) -> None:
        runbook = self.catalog_backed_runbook()
        runbook["commands"][0]["catalog_command_id"] = "made_up_command"

        response = TestClient(app).post(
            "/api/runbooks/generated",
            json={"runbook": runbook},
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("unknown catalog command_id", response.json()["detail"])

    def test_receive_generated_runbook_rejects_mismatched_command(self) -> None:
        runbook = self.catalog_backed_runbook()
        runbook["commands"][0]["command"] = "TO_DISABLE_OUTPUT"

        response = TestClient(app).post(
            "/api/runbooks/generated",
            json={"runbook": runbook},
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("command must match catalog value", response.json()["detail"])

    def test_receive_generated_runbook_rejects_disallowed_args(self) -> None:
        runbook = self.catalog_backed_runbook()
        runbook["commands"][0]["args"][1]["default"] = 9999

        response = TestClient(app).post(
            "/api/runbooks/generated",
            json={"runbook": runbook},
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("default is not allowed", response.json()["detail"])

    def test_receive_generated_runbook_rejects_empty_generated_commands(self) -> None:
        response = TestClient(app).post(
            "/api/runbooks/generated",
            json={"runbook": self.catalog_backed_runbook(commands=[])},
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("must include command steps", response.json()["detail"])

    def test_upload_runbook_inserts_uploaded_status(self) -> None:
        response = TestClient(app).post(
            "/api/runbooks/upload",
            json={
                "runbook": {
                    "report_id": "report_123",
                    "title": "Upload reviewed command plan",
                    "summary": "Ready for Supabase persistence.",
                }
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "uploaded")
        insert_call = self.client.queries["command_runbooks"].calls[-1]
        self.assertEqual(insert_call[0], "insert")
        self.assertEqual(insert_call[1]["status"], "uploaded")


if __name__ == "__main__":
    unittest.main()
