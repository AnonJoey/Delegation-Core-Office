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
        self.assertEqual(status["cores_active"], ["agent-harness-core", "multimodal-media-core", "local-platform-core", "self-hosted-catalog"])
        # So o que existe de verdade: nada de OCR, Whisper, Audiblez nem orquestrador.
        self.assertEqual(status["multimodal_capabilities"], ["document conversion to Markdown"])
        self.assertNotIn("orchestrator", status)
        self.assertEqual(status["skills"]["total_indexed"], 5)

    def test_homelab_gateway_facade(self):
        catalog = self.bridge.list_homelab_services()
        self.assertEqual(len(catalog), 29)
        self.assertFalse(hasattr(self.bridge, "route_homelab_service"))

    def test_skills_search_and_sanitization(self):
        res = self.bridge.search_skills("python", limit=2)
        self.assertGreater(len(res), 0)

        raw = "Let us delve into this game-changer framework."
        san = self.bridge.sanitize_text(raw)
        self.assertFalse(san["is_clean"])
        self.assertNotIn("delve", san["purified"])

if __name__ == "__main__":
    unittest.main()
