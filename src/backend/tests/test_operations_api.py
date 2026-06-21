from __future__ import annotations

import unittest
from typing import Any

from fastapi.testclient import TestClient

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

    def upsert(self, rows: list[dict[str, Any]], on_conflict: str):
        self.calls.append(("upsert", (rows, on_conflict)))
        self.data = rows
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

    def test_receive_generated_runbook_inserts_generated_status(self) -> None:
        response = TestClient(app).post(
            "/api/runbooks/generated",
            json={
                "runbook": {
                    "report_id": "report_123",
                    "satellite_external_id": "real-25544",
                    "title": "Monitor ISS drag risk",
                    "commands": [{"step": "hold", "command": "NOOP"}],
                }
            },
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "accepted")
        insert_call = self.client.queries["command_runbooks"].calls[-1]
        self.assertEqual(insert_call[0], "insert")
        self.assertEqual(insert_call[1]["status"], "generated")

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
