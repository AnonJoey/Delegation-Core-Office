"""tests/test_dashboard_api_cores.py — Testes automatizados para os endpoints
dos Cores Unificados adicionados em dashboard_api.py (Agent Harness, Multimodal,
Orchestration, Local Platform).
"""

import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest
from tests._dashboard_auth import AUTH

from delegation_core import dashboard_api
from delegation_core.config import Config
import pytest

pytestmark = pytest.mark.usefixtures("catalogo_de_skills")
from delegation_core.tracker import ProcessTracker


class FakeVault:
    def get_stats(self):
        return {"indexed_notes": 10}


@pytest.fixture
def server(monkeypatch, tmp_path):
    import delegation_core.config as config_mod
    monkeypatch.setattr(config_mod, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_mod, "CONFIG_FILE", tmp_path / "config.json")
    vault_path = tmp_path / "vault"
    vault_path.mkdir()
    cfg = Config(vault_path=str(vault_path), vault_folders=["reference"])
    fake_vault = FakeVault()
    monkeypatch.setattr(dashboard_api, "_cfg", cfg)
    monkeypatch.setattr(dashboard_api, "_vault", fake_vault)
    monkeypatch.setattr(dashboard_api, "_tracker", ProcessTracker(tmp_path / "processes.json"))

    srv = ThreadingHTTPServer(("127.0.0.1", 0), dashboard_api._Handler)
    port = srv.server_address[1]
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield port, cfg
    srv.shutdown()
    srv.server_close()


def _get(port, path):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", path, headers=AUTH)
    res = conn.getresponse()
    body = json.loads(res.read())
    conn.close()
    return res.status, body


def _post(port, path, payload):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {**AUTH, "Content-Type": "application/json"}
    conn.request("POST", path, headers=headers, body=json.dumps(payload))
    res = conn.getresponse()
    body = json.loads(res.read())
    conn.close()
    return res.status, body


def test_cores_status(server):
    port, _ = server
    status, body = _get(port, "/api/cores/status")
    assert status == 200
    assert body["status"] == "OPERATIONAL"
    assert "agent-harness-core" in body["cores_active"]
    assert "orchestration-core" not in body["cores_active"]


def test_cores_skills_search(server):
    port, _ = server
    status, body = _get(port, "/api/cores/skills?q=python&limit=5")
    assert status == 200
    assert "results" in body
    assert body["count"] == len(body["results"])
    assert body["count"] <= 5


def test_cores_skill_by_id(server):
    port, _ = server
    status, body = _get(port, "/api/cores/skill?id=1")
    assert status in (200, 404)
    if status == 200:
        assert "name" in body or "title" in body


def test_cores_hardware(server):
    port, _ = server
    status, body = _get(port, "/api/cores/hardware")
    assert status == 200
    assert body["disk_home"]["total_gb"] > 0 and 0 <= body["disk_home"]["used_pct"] <= 100
    # Sem rotulo de hardware inventado nem saude afirmada sem checagem.
    assert "nvme_corsair_mp600" not in body and "status" not in body


def test_cores_sanitize_post(server):
    port, _ = server
    status, body = _post(port, "/api/cores/sanitize", {"text": "This is a revolutionary dynamic system."})
    assert status == 200
    assert "audit" in body
    assert "purified" in body
    assert "score" in body


def test_cores_prune(server):
    port, _ = server
    status, body = _post(port, "/api/cores/prune", {"text": "def foo():\n    pass\n"})
    assert status == 200
    assert "reduced_text" in body or "reduction_ratio" in body
