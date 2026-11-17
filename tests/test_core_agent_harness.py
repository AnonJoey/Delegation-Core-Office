import unittest
from delegation_core.cores.agent_harness.server import AgentHarnessServer
import pytest

pytestmark = pytest.mark.usefixtures("catalogo_de_skills")

class TestAgentHarnessCore(unittest.TestCase):
    def setUp(self):
        self.server = AgentHarnessServer()

    def test_status(self):
        res = self.server.handle_rpc("system.status", {})
        self.assertEqual(res["server"], "agent-harness-core")
        self.assertIn("ECC", res["skills_indexed"])
        self.assertEqual(res["skills_indexed"]["ECC"]["count"], 3)

    def test_skills_search(self):
        res = self.server.handle_rpc("skills.search", {"query": "git commit", "limit": 3})
        self.assertGreater(len(res["results"]), 0)

    def test_sanitizer(self):
        raw = "We seamlessly delve into the robust code."
        audit = self.server.handle_rpc("sanitizer.audit", {"text": raw})
        self.assertFalse(audit["is_clean"])
        self.assertIn("delve", audit["slop_detected"])
        
        purified = self.server.handle_rpc("sanitizer.purify", {"text": raw})
        self.assertNotIn("delve", purified["cleaned"])

if __name__ == "__main__":
    unittest.main()
