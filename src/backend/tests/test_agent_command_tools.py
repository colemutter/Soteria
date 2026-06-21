from __future__ import annotations

import json
import unittest

from agent.definition import SOTERIA_AGENTS
from agent.tools import (
    draft_satellite_command_plan,
    get_satellite_command,
)


def tool_payload(response):
    return json.loads(response["content"][0]["text"])


class AgentCommandToolsTest(unittest.IsolatedAsyncioTestCase):
    async def test_get_satellite_command_returns_catalog_data(self) -> None:
        response = await get_satellite_command.handler(
            {"command_id": "sample_disable"}
        )
        payload = tool_payload(response)

        self.assertNotIn("is_error", response)
        self.assertEqual(
            payload["catalog_version"],
            "nos3-openc3-v1_07_04-cmdcat.20260621",
        )
        self.assertEqual(payload["command_count"], 1)
        command = payload["commands"][0]
        self.assertEqual(command["catalog_command_id"], "sample_disable")
        self.assertEqual(command["target"], "SAMPLE_RADIO")
        self.assertEqual(command["command"], "SAMPLE_DISABLE_CC")
        self.assertEqual(command["args"], [])
        self.assertTrue(command["automated_allowed"])
        self.assertFalse(command["human_review_required"])
        self.assertEqual(
            command["verifier"],
            {
                "target": "SAMPLE_RADIO",
                "packet": "SAMPLE_HK_TLM",
                "item": "DEVICE_ENABLED",
                "condition": "equals:DISABLED",
            },
        )
        self.assertIn(
            'cmd("SAMPLE_RADIO SAMPLE_DISABLE_CC")',
            command["ruby_rendering"]["ruby"],
        )

    async def test_get_satellite_command_rejects_unknown_ids(self) -> None:
        response = await get_satellite_command.handler(
            {"command_id": "not_in_catalog"}
        )
        payload = tool_payload(response)

        self.assertTrue(response["is_error"])
        self.assertIn("unknown catalog command IDs", payload["detail"])

    async def test_draft_plan_rejects_free_form_target_command_mismatch(self) -> None:
        response = await draft_satellite_command_plan.handler(
            {
                "satellite_id": "sat-1",
                "objective": "Protect payload.",
                "command_id": "sample_disable",
                "target": "CFS_RADIO",
                "command": "TO_DISABLE_OUTPUT",
            }
        )
        payload = tool_payload(response)

        self.assertTrue(response["is_error"])
        self.assertIn("target mismatch", payload["detail"])
        self.assertEqual(payload["plan_status"], "DRAFT / HUMAN REVIEW REQUIRED")

    async def test_draft_plan_includes_catalog_ids_verifiers_and_ruby(
        self,
    ) -> None:
        response = await draft_satellite_command_plan.handler(
            {
                "satellite_id": "sat-1",
                "objective": "Protect sample payload from noisy data collection.",
                "constraints": ["simulator-only", "operator review required"],
                "command_ids": ["sample_disable", "adcs_set_sunsafe"],
            }
        )
        payload = tool_payload(response)

        self.assertNotIn("is_error", response)
        self.assertEqual(payload["plan_status"], "DRAFT / HUMAN REVIEW REQUIRED")
        self.assertTrue(payload["human_review_required"])
        self.assertFalse(payload["execution_allowed"])
        self.assertEqual(
            [command["catalog_command_id"] for command in payload["commands"]],
            ["sample_disable", "adcs_set_sunsafe"],
        )
        self.assertEqual(
            payload["commands"][0]["verifier"]["item"],
            "DEVICE_ENABLED",
        )
        self.assertEqual(
            payload["commands"][1]["verifier"]["item"],
            "MODE",
        )
        ruby = payload["ruby_runbook"]["ruby"]
        self.assertIn('cmd("SAMPLE_RADIO SAMPLE_DISABLE_CC")', ruby)
        self.assertIn("GENERIC_ADCS_SET_MODE_CC", ruby)
        self.assertNotIn("cmd_no_checks", ruby)
        self.assertNotIn("cmd_no_hazardous_check", ruby)

    async def test_draft_plan_rejects_free_form_command_without_catalog_id(self) -> None:
        response = await draft_satellite_command_plan.handler(
            {
                "satellite_id": "sat-1",
                "objective": "Free-form command should not be accepted.",
                "target": "SAMPLE_RADIO",
                "command": "SAMPLE_DISABLE_CC",
            }
        )
        payload = tool_payload(response)

        self.assertTrue(response["is_error"])
        self.assertIn("catalog_command_id", payload["detail"])

    def test_satellite_command_agent_prompt_requires_catalog_contract(self) -> None:
        prompt = SOTERIA_AGENTS["satellite-command-agent"].prompt

        self.assertIn("catalog_command_id", prompt)
        self.assertIn("DRAFT / HUMAN REVIEW REQUIRED", prompt)
        self.assertIn("Do not invent OpenC3", prompt)
        self.assertIn("cmd_no_checks", prompt)
        self.assertIn("cmd_no_hazardous_check", prompt)


if __name__ == "__main__":
    unittest.main()
