import unittest
import asyncio
from delegation_core.cores.unified_facade import get_cores_bridge
import pytest

pytestmark = pytest.mark.usefixtures("catalogo_de_skills")

class TestUnifiedCoresSuite(unittest.TestCase):
    def setUp(self):
        self.bridge = get_cores_bridge()

    def test_unified_status(self):
        status = self.bridge.get_unified_status()
        self.assertEqual(status["status"], "OPERATIONAL")
        self.assertEqual(len(status["cores_active"]), 5)
        self.assertIn("agent-harness-core", status["cores_active"])
        self.assertIn("multimodal-media-core", status["cores_active"])
        self.assertIn("orchestration-core", status["cores_active"])
        self.assertIn("local-platform-core", status["cores_active"])
        self.assertIn("homelab-gateway-core", status["cores_active"])
        self.assertEqual(status["skills"]["total_indexed"], 5)

    def test_homelab_gateway_facade(self):
        catalog = self.bridge.list_homelab_services()
        self.assertEqual(len(catalog), 29)
        routed = self.bridge.route_homelab_service("supabase", "query", user_token="admin_key")
        self.assertEqual(routed["status"], "FORWARDED_OK")
        self.assertEqual(routed["port"], 8000)

    def test_skills_search_and_sanitization(self):
        res = self.bridge.search_skills("python", limit=2)
        self.assertGreater(len(res), 0)

        raw = "Let us delve into this game-changer framework."
        san = self.bridge.sanitize_text(raw)
        self.assertFalse(san["is_clean"])
        self.assertNotIn("delve", san["purified"])

    def test_diagram_and_tts(self):
        diag = self.bridge.generate_diagram("Arquitetura de microsservicos")
        self.assertEqual(diag["status"], "SUCCESS")
        self.assertIn("mermaid_code", diag)

        tts = self.bridge.synthesize_speech("Execucao do teste automatizado")
        self.assertEqual(tts["status"], "SUCCESS")

    def test_agent_session_and_token_prune(self):
        session = self.bridge.execute_agent_session("suite_test_1", "# Comentario para remover\n x = 42")
        self.assertEqual(session["execution_status"], "SUCCESS")

        pruned = self.bridge.prune_context("   Texto com    espacos   redundantes\n\n\n\n")
        self.assertNotIn("\n\n\n\n", pruned["pruned_text"])

    def test_orchestration_workflow(self):
        async def work_node():
            return "node_done"

        steps = [{"name": "worker", "action": work_node}]
        res = asyncio.run(self.bridge.execute_task_workflow("suite_workflow", steps))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["dag_nodes_executed"], 1)

if __name__ == "__main__":
    unittest.main()
