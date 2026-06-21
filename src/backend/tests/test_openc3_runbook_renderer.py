from __future__ import annotations

import unittest

from agent.openc3_runbook_renderer import (
    SCRIPT_FORMAT_VERSION,
    render_openc3_ruby_command,
    render_openc3_ruby_runbook,
)


class OpenC3RunbookRendererTest(unittest.TestCase):
    def test_renders_no_arg_sample_disable_command(self) -> None:
        rendered = render_openc3_ruby_command("sample_disable")

        self.assertEqual(rendered["script_language"], "ruby")
        self.assertEqual(
            rendered["script_format_version"],
            SCRIPT_FORMAT_VERSION,
        )
        self.assertEqual(rendered["catalog_command_id"], "sample_disable")
        self.assertEqual(rendered["target"], "SAMPLE_RADIO")
        self.assertEqual(rendered["command"], "SAMPLE_DISABLE_CC")
        self.assertEqual(rendered["args"], [])
        self.assertIn(
            'cmd("SAMPLE_RADIO SAMPLE_DISABLE_CC")',
            rendered["ruby"],
        )
        self.assertIn(
            "# Soteria simulator-only OpenC3 Ruby runbook snippet.",
            rendered["ruby"],
        )
        self.assertIn(
            "# Human-reviewable; verify the catalog command before simulator use.",
            rendered["ruby"],
        )

    def test_renders_typed_args_for_radio_enable_output(self) -> None:
        rendered = render_openc3_ruby_command("radio_enable_output")

        self.assertEqual(
            rendered["args"],
            [
                {"name": "DEST_IP", "type": "STRING", "value": "radio-sim"},
                {"name": "DEST_PORT", "type": "UINT16", "value": 5011},
            ],
        )
        self.assertIn(
            (
                'cmd("CFS_RADIO TO_ENABLE_OUTPUT with '
                "DEST_IP 'radio-sim', DEST_PORT 5011\")"
            ),
            rendered["ruby"],
        )

    def test_includes_catalog_verifier_telemetry_snippet(self) -> None:
        rendered = render_openc3_ruby_command("sample_disable")

        self.assertEqual(
            rendered["verifier"],
            {
                "target": "SAMPLE_RADIO",
                "packet": "SAMPLE_HK_TLM",
                "item": "DEVICE_ENABLED",
                "condition": "equals:DISABLED",
            },
        )
        self.assertIn(
            'tlm("SAMPLE_RADIO SAMPLE_HK_TLM DEVICE_ENABLED")',
            rendered["ruby"],
        )
        self.assertIn(
            "# Catalog verifier: equals:DISABLED",
            rendered["ruby"],
        )
        self.assertIn(
            'unless sample_disable_device_enabled.to_s == "DISABLED"',
            rendered["ruby"],
        )

    def test_forbidden_no_check_helpers_are_absent(self) -> None:
        rendered = render_openc3_ruby_runbook(
            ["sample_disable", "radio_enable_output"]
        )

        self.assertEqual(rendered["script_language"], "ruby")
        self.assertEqual(
            rendered["script_format_version"],
            SCRIPT_FORMAT_VERSION,
        )
        self.assertNotIn("cmd_no_checks", rendered["ruby"])
        self.assertNotIn("cmd_no_hazardous_check", rendered["ruby"])
        self.assertNotIn("UDPSocket", rendered["ruby"])
        self.assertNotIn("http://", rendered["ruby"])
        self.assertNotIn("https://", rendered["ruby"])

    def test_unresolved_command_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot render executable Ruby"):
            render_openc3_ruby_command("eps_load_shed_policy")


if __name__ == "__main__":
    unittest.main()
