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

    def test_route_authorized(self):
        res = self.gateway.route_request("immich", action="upload_photo", user_token="valid_secret_token")
        self.assertEqual(res["status"], "FORWARDED_OK")
        self.assertEqual(res["target_service"], "immich")
        self.assertEqual(res["port"], 2283)

    def test_route_unauthorized(self):
        res = self.gateway.route_request("vaultwarden", action="get_secret", user_token="")
        self.assertEqual(res["status"], "UNAUTHORIZED")

    def test_route_not_found(self):
        res = self.gateway.route_request("non_existent_service", action="ping")
        self.assertEqual(res["status"], "NOT_FOUND")

    def test_route_case_insensitivity_formerly_mixed_case(self):
        for svc in ["LibreChat", "librechat", "AppFlowy", "appflowy", "LibreTranslate", "FreshRSS"]:
            res = self.gateway.route_request(svc, action="status", user_token="admin_token")
            self.assertEqual(res["status"], "FORWARDED_OK", f"Failed to route {svc}")

    def test_health_check(self):
        health = self.gateway.check_health()
        self.assertEqual(health["status"], "HEALTHY")
        self.assertEqual(health["total_services"], 29)
        self.assertGreater(health["domains_count"], 5)

if __name__ == "__main__":
    unittest.main()
