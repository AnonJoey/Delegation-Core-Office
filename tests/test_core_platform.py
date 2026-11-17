import unittest
from delegation_core.cores.platform.platform_engine import UnifiedLocalPlatform

class TestLocalPlatformCore(unittest.TestCase):
    def setUp(self):
        self.platform = UnifiedLocalPlatform()

    def test_agent_session_flow(self):
        res = self.platform.execute_agent_session("sess_test_10", "// comentario \n print('ok')")
        self.assertEqual(res["execution_status"], "SUCCESS")
        self.assertEqual(res["hardware_telemetry"]["status"], "HEALTHY")
        self.assertTrue(res["agent_guard"]["budget"]["within_budget"])

    def test_pruning(self):
        raw = "// Comentario desnecessario \n var x = 10;"
        res = self.platform.pruner.prune_context(raw)
        self.assertNotIn("// Comentario", res["pruned_text"])

    def test_pruning_preserves_markdown_headers_and_urls(self):
        raw = "# Titulo Principal\n## Subtitulo\nVer https://github.com/test e file:///home/joey/doc\n// comentario\nx = 1 # inline"
        res = self.platform.pruner.prune_context(raw)
        self.assertIn("# Titulo Principal", res["pruned_text"])
        self.assertIn("## Subtitulo", res["pruned_text"])
        self.assertIn("https://github.com/test", res["pruned_text"])
        self.assertIn("file:///home/joey/doc", res["pruned_text"])
        self.assertNotIn("// comentario", res["pruned_text"])
        self.assertNotIn("# inline", res["pruned_text"])

if __name__ == "__main__":
    unittest.main()
