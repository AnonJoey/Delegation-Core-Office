import json
import unittest
from delegation_core.server import (
    cores_unified_status,
    cores_skills_search,
    cores_sanitize_prompt,
    cores_multimodal_ingest,
    cores_platform_session,
    cores_prune_context,
    cores_selfhosted_catalog,
    cores_selfhosted_route,
)

import pytest

pytestmark = pytest.mark.usefixtures("catalogo_de_skills")

class TestUnifiedCoresMCPTools(unittest.TestCase):
    def test_cores_unified_status(self):
        raw = cores_unified_status()
        data = json.loads(raw)
        self.assertEqual(data["status"], "OPERATIONAL")
        self.assertEqual(len(data["cores_active"]), 5)
        self.assertIn("homelab-gateway-core", data["cores_active"])

    def test_cores_skills_search(self):
        raw = cores_skills_search("git", limit=2)
        data = json.loads(raw)
        self.assertEqual(data["status"], "ok")
        self.assertGreater(data["count"], 0)

    def test_cores_sanitize_prompt(self):
        raw = cores_sanitize_prompt("We delve into robust code.")
        data = json.loads(raw)
        self.assertFalse(data["is_clean"])
        self.assertNotIn("delve", data["purified"])

    def test_cores_platform_session(self):
        raw = cores_platform_session("mcp_sess_1", "print('hello')")
        data = json.loads(raw)
        self.assertEqual(data["execution_status"], "SUCCESS")

    def test_cores_prune_context(self):
        raw = cores_prune_context("line 1\n\n\n\n\nline 2")
        data = json.loads(raw)
        self.assertIn("tokens_saved_estimate", data)

    def test_cores_selfhosted_catalog(self):
        raw = cores_selfhosted_catalog()
        data = json.loads(raw)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["count"], 29)

    def test_cores_selfhosted_route(self):
        raw = cores_selfhosted_route("immich", "ping", "test-token-admin")
        data = json.loads(raw)
        self.assertEqual(data["status"], "FORWARDED_OK")
        self.assertEqual(data["target_service"], "immich")

if __name__ == "__main__":
    unittest.main()
