from __future__ import annotations

import unittest

from scripts.render_poller_pipeline_validation import parse_supabase_json


class RenderPollerPipelineValidationTest(unittest.TestCase):
    def test_parse_supabase_json_accepts_cli_noise_and_multiple_objects(self) -> None:
        output = """
Using workdir /Users/example/Projects/Soteria
{"advisory": {"id": "rls_disabled"}}
{
  "boundary": "abc",
  "rows": [
    {"ok": 1}
  ],
  "warning": "untrusted"
}
"""

        self.assertEqual(parse_supabase_json(output)["rows"], [{"ok": 1}])


if __name__ == "__main__":
    unittest.main()
