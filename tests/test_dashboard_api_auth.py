"""A API do dashboard exige o bearer token do daemon em toda requisicao.

Medido nesta maquina em 14/10/2026, contra o daemon real: GET /api/status,
/api/processes e /api/vault/tree responderam 200 sem credencial nenhuma, e as
rotas POST (`/api/vault/note/save`, `/api/llama/start`, `/api/config/update`)
so eram protegidas por loopback e pela allowlist de Origin. Isso nao cobre um
processo local qualquer, nem nenhum cliente quando `server_host` deixa de ser
127.0.0.1, que e o caso do daemon num servidor.

O preflight CORS fica isento de proposito: o navegador o envia sem credencial e
ele so informa quais cabecalhos a requisicao real pode levar.
"""
import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from delegation_core import dashboard_api
from delegation_core.tracker import ProcessTracker
from tests._dashboard_auth import AUTH, TOKEN


@pytest.fixture
def server(monkeypatch, tmp_path):
    tracker = ProcessTracker(tmp_path / "processes.json")
    monkeypatch.setattr(dashboard_api, "_tracker", tracker)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), dashboard_api._Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1], tracker
    srv.shutdown()
    srv.server_close()


def _call(port, method, path, headers=None, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(method, path, body=body, headers=headers or {})
    res = conn.getresponse()
    raw = res.read()
    out = (res.status, dict(res.getheaders()), json.loads(raw) if raw else None)
    conn.close()
    return out


def test_rejects_a_get_with_no_credential(server):
    port, _ = server
    status, headers, body = _call(port, "GET", "/api/processes")
    assert status == 401
    assert "bearer" in body["error"].lower()


def test_rejects_a_post_with_no_credential_and_does_not_run_it(server):
    port, tracker = server
    payload = json.dumps({"name": "intruso", "description": "", "steps": ""})
    status, _, _ = _call(port, "POST", "/api/processes/create",
                         headers={"Content-Type": "application/json"}, body=payload)
    assert status == 401
    assert tracker.list_processes(status="all") == []
    # A mesma chamada, com o token, e aceita: prova que o 401 acima foi a
    # autenticacao e nao um erro de rota ou de corpo.
    status, _, _ = _call(port, "POST", "/api/processes/create",
                         headers={**AUTH, "Content-Type": "application/json"}, body=payload)
    assert status == 201
    assert [p["name"] for p in tracker.list_processes(status="all")] == ["intruso"]


@pytest.mark.parametrize("header", [
    "Bearer token-errado",
    "Bearer ",
    "Bearer",
    f"Basic {TOKEN}",
    TOKEN,
    "Bearer tokén-não-ascii",
])
def test_rejects_wrong_or_malformed_credentials(server, header):
    port, _ = server
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest("GET", "/api/processes")
    conn.putheader("Authorization", header.encode("utf-8"))
    conn.endheaders()
    res = conn.getresponse()
    res.read()
    conn.close()
    assert res.status == 401


def test_accepts_the_token_and_the_scheme_is_case_insensitive(server):
    port, _ = server
    assert _call(port, "GET", "/api/processes", headers=AUTH)[0] == 200
    lower = {"Authorization": f"bearer {TOKEN}"}
    assert _call(port, "GET", "/api/processes", headers=lower)[0] == 200


def test_an_empty_server_token_rejects_everything_including_an_empty_bearer(server, monkeypatch):
    port, _ = server
    monkeypatch.setattr(dashboard_api, "_token", "")
    assert _call(port, "GET", "/api/processes", headers=AUTH)[0] == 401
    assert _call(port, "GET", "/api/processes", headers={"Authorization": "Bearer "})[0] == 401


def test_preflight_needs_no_credential_and_allows_the_authorization_header(server):
    port, _ = server
    status, headers, _ = _call(port, "OPTIONS", "/api/processes/create",
                               headers={"Origin": "tauri://localhost"})
    assert status == 204
    assert "Authorization" in headers["Access-Control-Allow-Headers"]


def test_the_401_still_carries_cors_so_the_webview_can_read_it(server):
    port, _ = server
    _, headers, _ = _call(port, "GET", "/api/processes",
                          headers={"Origin": "tauri://localhost"})
    assert headers.get("Access-Control-Allow-Origin") == "tauri://localhost"
