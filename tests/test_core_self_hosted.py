import unittest
from delegation_core.cores.self_hosted import HomelabServiceGateway

class TestCoreSelfHosted(unittest.TestCase):
    def setUp(self):
        self.gateway = HomelabServiceGateway()

    def test_catalog_count(self):
        services = self.gateway.list_services()
        self.assertEqual(len(services), 29)

    def test_filter_by_domain(self):
        storage_services = self.gateway.list_services(domain="storage_media")
        names = [s["name"] for s in storage_services]
        self.assertIn("immich", names)
        self.assertIn("jellyfin", names)
        self.assertIn("paperless-ngx", names)

if __name__ == "__main__":
    unittest.main()

    def test_resumo_nao_diz_que_algo_esta_no_ar(self):
        """O catalogo e uma lista fixa: o resumo conta, nao afirma saude de servico nenhum."""
        r = self.gateway.summary()
        self.assertEqual(r["total_services"], 29)
        self.assertNotIn("status", r)
        self.assertFalse(hasattr(self.gateway, "route_request"))
