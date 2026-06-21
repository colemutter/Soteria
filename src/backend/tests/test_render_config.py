from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
RENDER_YAML = REPO_ROOT / "render.yaml"


class RenderConfigTest(unittest.TestCase):
    def test_poller_reaction_url_uses_batch_report_endpoint(self) -> None:
        text = RENDER_YAML.read_text()

        self.assertIn("SOTERIA_REACTION_SERVICE_URL", text)
        self.assertIn(
            "value: https://soteria-backend-7360.onrender.com/api/poller/report",
            text,
        )
        self.assertNotIn(
            "value: https://soteria-backend-7360.onrender.com/agent/reactions",
            text,
        )

    def test_frontend_and_poller_share_render_backend_base_url(self) -> None:
        text = RENDER_YAML.read_text()

        poller_match = re.search(
            r"SOTERIA_REACTION_SERVICE_URL\s*\n\s*value:\s*(https://[^\s]+/api/poller/report)",
            text,
        )
        frontend_match = re.search(
            r"VITE_API_BASE_URL\s*\n\s*value:\s*(https://[^\s]+)",
            text,
        )

        self.assertIsNotNone(poller_match)
        self.assertIsNotNone(frontend_match)
        assert poller_match is not None
        assert frontend_match is not None

        poller_base_url = poller_match.group(1).removesuffix("/api/poller/report")
        self.assertEqual(frontend_match.group(1), poller_base_url)


if __name__ == "__main__":
    unittest.main()
