"""Proxy de API: provedor falso de verdade (HTTP local), proxy de verdade na frente.

Confere o que interessa num proxy de API: o resultado de ferramenta grande chega
comprimido ao provedor, o resto da requisicao e a autenticacao chegam intactos,
a resposta (inclusive streaming SSE) volta byte a byte, a mesma entrada gera o
mesmo corpo em turnos seguidos (cache do provedor), e o livro-caixa registra.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from types import SimpleNamespace

import httpx
import pytest
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import StreamingResponse
from starlette.routing import Route

from delegation_core.livro import LivroCaixa
from delegation_core.proxy.reescrita import reescrever
from delegation_core.proxy.servidor import criar_app

SSE = b"event: message_start\ndata: {\"type\":\"message_start\"}\n\nevent: content_block_delta\ndata: {\"delta\":\"ol\xc3\xa1\"}\n\n"
GREP = "\n".join(f"src/m{i % 7}.py:{i}:    value_{i} = compute({i})" for i in range(600))


def _porta():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _subir(app, porta):
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=porta, log_level="error", lifespan="off"))
    srv.install_signal_handlers = lambda: None
    threading.Thread(target=srv.run, daemon=True).start()
    for _ in range(100):
        if srv.started:
            return srv
        time.sleep(0.05)
    raise RuntimeError("servidor nao subiu")


@pytest.fixture
def cenario(tmp_path):
    recebidos = []

    async def provedor(req: Request):
        recebidos.append({"path": req.url.path, "headers": dict(req.headers), "body": await req.body()})

        async def gerar():
            for i in range(0, len(SSE), 7):
                yield SSE[i:i + 7]
        return StreamingResponse(gerar(), media_type="text/event-stream", headers={"x-request-id": "req_1"})

    p_prov, p_proxy = _porta(), _porta()
    prov = _subir(Starlette(routes=[Route("/{c:path}", provedor, methods=["GET", "POST"])]), p_prov)
    cfg = SimpleNamespace(proxy_min_chars=2000, proxy_upstream_anthropic=f"http://127.0.0.1:{p_prov}",
                          proxy_upstream_openai=f"http://127.0.0.1:{p_prov}")
    livro = LivroCaixa(tmp_path / "livro.sqlite3")
    proxy = _subir(criar_app(cfg, livro), p_proxy)
    yield SimpleNamespace(url=f"http://127.0.0.1:{p_proxy}", recebidos=recebidos, livro=livro)
    proxy.should_exit = prov.should_exit = True


def _anthropic():
    return {"model": "claude-x", "max_tokens": 100, "stream": True, "system": "seja breve",
            "messages": [{"role": "user", "content": "procure compute"},
                         {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "rg compute"}}]},
                         {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": GREP,
                                                       "cache_control": {"type": "ephemeral"}},
                                                      {"type": "text", "text": "e agora?"}]}]}


def test_anthropic_streaming_comprime_e_repassa(cenario):
    r = httpx.post(cenario.url + "/v1/messages", json=_anthropic(),
                   headers={"x-api-key": "sk-ant-TESTE", "anthropic-version": "2023-06-01"}, timeout=60)
    assert r.status_code == 200 and r.content == SSE, "a resposta volta byte a byte"
    assert r.headers["x-request-id"] == "req_1"
    rec = cenario.recebidos[-1]
    assert rec["headers"]["x-api-key"] == "sk-ant-TESTE" and rec["headers"]["anthropic-version"] == "2023-06-01"
    corpo = json.loads(rec["body"])
    tr = corpo["messages"][2]["content"][0]
    assert len(tr["content"]) < len(GREP) / 5 and "Retrieve more: hash=" in tr["content"]
    assert tr["cache_control"] == {"type": "ephemeral"} and tr["tool_use_id"] == "t1"
    assert corpo["messages"][2]["content"][1] == {"type": "text", "text": "e agora?"}
    assert corpo["system"] == "seja breve" and corpo["messages"][0]["content"] == "procure compute"
    rel = cenario.livro.relatorio()
    assert [f["ferramenta"] for f in rel["ferramentas"]] == ["proxy:anthropic"]


def test_mesma_entrada_mesmo_corpo_em_turnos_seguidos(cenario):
    for _ in range(2):
        httpx.post(cenario.url + "/v1/messages", json=_anthropic(), timeout=60)
    assert cenario.recebidos[-1]["body"] == cenario.recebidos[-2]["body"]


def test_resultado_pequeno_e_corpo_sem_ferramenta_passam_intactos(cenario):
    pequeno = {"model": "m", "messages": [{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "a", "content": "ok"}]}]}
    bruto = json.dumps(pequeno, indent=2).encode()
    httpx.post(cenario.url + "/v1/messages", content=bruto, headers={"content-type": "application/json"}, timeout=60)
    assert cenario.recebidos[-1]["body"] == bruto, "sem compressao, nem a formatacao do JSON muda"
    httpx.get(cenario.url + "/v1/models?limit=2", timeout=60)
    assert cenario.recebidos[-1]["path"] == "/v1/models"


def test_formatos_openai():
    rel_chat = reescrever("/v1/chat/completions", {"messages": [{"role": "tool", "tool_call_id": "c", "content": GREP},
                                                                 {"role": "user", "content": GREP}]}, 2000)
    assert len(rel_chat[0]["messages"][0]["content"]) < len(GREP) and rel_chat[0]["messages"][1]["content"] == GREP
    rel_resp = reescrever("/v1/responses", {"input": [{"type": "function_call_output", "call_id": "c", "output": GREP},
                                                      {"type": "message", "content": GREP}]}, 2000)
    assert len(rel_resp[0]["input"][0]["output"]) < len(GREP) and rel_resp[0]["input"][1]["content"] == GREP
    assert rel_resp[1].formato == "openai_responses" and rel_resp[1].comprimidos == 1


def test_provedor_fora_do_ar_da_502(tmp_path):
    p = _porta()
    cfg = SimpleNamespace(proxy_min_chars=2000, proxy_upstream_anthropic=f"http://127.0.0.1:{_porta()}",
                          proxy_upstream_openai="http://127.0.0.1:1")
    srv = _subir(criar_app(cfg), p)
    try:
        r = httpx.post(f"http://127.0.0.1:{p}/v1/messages", json={"messages": []}, timeout=60)
        assert r.status_code == 502 and r.json()["error"]["type"] == "proxy_upstream_error"
    finally:
        srv.should_exit = True


def test_nao_loga_corpo_nem_chave(cenario, caplog):
    import logging
    caplog.set_level(logging.DEBUG)
    httpx.post(cenario.url + "/v1/messages", json=_anthropic(), headers={"x-api-key": "sk-ant-SEGREDO"}, timeout=60)
    texto = caplog.text
    assert "SEGREDO" not in texto and "value_42" not in texto
