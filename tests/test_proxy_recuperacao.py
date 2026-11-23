"""Recuperacao automatica do original no proxy (6.3.3).

Provedor falso (httpx MockTransport) que se comporta como um modelo: se a ferramenta de
recuperacao veio no pedido e ainda nao ha resultado dela, chama a ferramenta com o hash do
ponteiro; quando o resultado chega, responde com o numero de linhas do original. O cliente tem de
receber so a resposta final, e o fluxo SSE tem de sair coerente (um message_start, indices de bloco
seguidos, um message_stop).
"""

from __future__ import annotations

import json
import random
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from starlette.testclient import TestClient

from delegation_core.compressao.ccr import Guarda
from delegation_core.proxy import recuperacao as rc
from delegation_core.proxy.servidor import criar_app

HEADROOM = Path.home() / "Projects" / "headroom"
H = "0123456789abcdef01234567"
ORIGINAL = "\n".join(f"linha {i} do log original" for i in range(250))


@pytest.fixture(autouse=True)
def _guardado():
    Guarda().put(H, ORIGINAL)


def _pedido_anthropic(stream: bool, extra_tools=None):
    corpo = {"model": "x", "max_tokens": 50, "stream": stream, "system": "seja breve",
             "messages": [
                 {"role": "user", "content": "rode o build"},
                 {"role": "assistant", "content": [{"type": "tool_use", "id": "b1", "name": "Bash", "input": {"command": "make"}}]},
                 {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "b1",
                                               "content": f"erro na linha 3\n[230 lines compressed to 20. Retrieve more: hash={H}]"}]}]}
    if extra_tools is not None:
        corpo["tools"] = extra_tools
    return corpo


def _pedido_openai(stream: bool):
    return {"model": "x", "stream": stream, "messages": [
        {"role": "user", "content": "rode o build"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "b1", "type": "function", "function": {"name": "Bash", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "b1", "content": f"erro\n[230 lines compressed to 20. Retrieve more: hash={H}]"}]}


# ── provedor falso ────────────────────────────────────────────────────────────

def _sse_anthropic(blocos: list[dict], stop: str) -> bytes:
    ev = [("message_start", {"type": "message_start", "message": {"id": "msg_1", "type": "message", "role": "assistant",
                                                                  "content": [], "model": "x", "usage": {"input_tokens": 10, "output_tokens": 1}}})]
    for i, b in enumerate(blocos):
        if b["type"] == "text":
            ev.append(("content_block_start", {"type": "content_block_start", "index": i, "content_block": {"type": "text", "text": ""}}))
            for k in range(0, len(b["text"]), 4):
                ev.append(("content_block_delta", {"type": "content_block_delta", "index": i, "delta": {"type": "text_delta", "text": b["text"][k:k + 4]}}))
        else:
            ev.append(("content_block_start", {"type": "content_block_start", "index": i,
                                               "content_block": {"type": "tool_use", "id": b["id"], "name": b["name"], "input": {}}}))
            js = json.dumps(b["input"])
            for k in range(0, len(js), 5):
                ev.append(("content_block_delta", {"type": "content_block_delta", "index": i, "delta": {"type": "input_json_delta", "partial_json": js[k:k + 5]}}))
        ev.append(("content_block_stop", {"type": "content_block_stop", "index": i}))
    ev.append(("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop}, "usage": {"output_tokens": 7}}))
    ev.append(("message_stop", {"type": "message_stop"}))
    return b"".join(f"event: {n}\ndata: {json.dumps(d)}\n\n".encode() for n, d in ev)


def _sse_openai(texto: str, chamadas: list[tuple[str, str, str]], fim: str) -> bytes:
    pedacos = [{"choices": [{"index": 0, "delta": {"role": "assistant"}}]}]
    for k in range(0, len(texto), 4):
        pedacos.append({"choices": [{"index": 0, "delta": {"content": texto[k:k + 4]}}]})
    for j, (cid, nome, args) in enumerate(chamadas):
        pedacos.append({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": j, "id": cid, "type": "function",
                                                                             "function": {"name": nome, "arguments": ""}}]}}]})
        for k in range(0, len(args), 5):
            pedacos.append({"choices": [{"index": 0, "delta": {"tool_calls": [{"index": j, "function": {"arguments": args[k:k + 5]}}]}}]})
    pedacos.append({"choices": [{"index": 0, "delta": {}, "finish_reason": fim}]})
    return b"".join(f"data: {json.dumps(p)}\n\n".encode() for p in pedacos) + b"data: [DONE]\n\n"


def _json(obj, status=200):
    """Resposta JSON como fluxo de bytes: o repasse do proxy le o corpo em streaming."""
    return httpx.Response(status, headers={"content-type": "application/json"},
                          stream=httpx.ByteStream(json.dumps(obj).encode()))


class Provedor:
    """O modelo falso. `misto` chama tambem uma ferramenta do cliente; `falhar_continuacao` da 500."""

    def __init__(self, misto=False, falhar_continuacao=False, sempre_chama=False):
        self.recebidos, self.misto, self.falhar, self.sempre = [], misto, falhar_continuacao, sempre_chama

    def _ja_tem_resultado(self, corpo, formato):
        ult = corpo["messages"][-1]
        if formato == "anthropic":
            return isinstance(ult.get("content"), list) and any(
                b.get("type") == "tool_result" and str(b.get("tool_use_id", "")).startswith("ccr") for b in ult["content"])
        return ult.get("role") == "tool" and str(ult.get("tool_call_id", "")).startswith("ccr")

    def __call__(self, req: httpx.Request):
        corpo = json.loads(req.content)
        self.recebidos.append(corpo)
        formato = "anthropic" if req.url.path == "/v1/messages" else "openai"
        tem_tool = any(rc._nome_da_ferramenta(t) == rc.NOME for t in corpo.get("tools") or [])
        if self._ja_tem_resultado(corpo, formato):
            if self.falhar:
                return _json(status=500, obj={"error": "caiu"})
            n = 0
            for m in corpo["messages"][::-1]:
                blocos = m.get("content") if isinstance(m.get("content"), list) else [m]
                for b in blocos:
                    texto = b.get("content") if isinstance(b, dict) else None
                    if isinstance(texto, str) and "original_content" in texto:
                        n = json.loads(texto)["original_content"].count("\n") + 1
                if n:
                    break
            if self.sempre:
                return self._chamada(corpo, formato)
            return self._final(corpo, formato, f"achei {n} linhas")
        if tem_tool:
            return self._chamada(corpo, formato)
        return self._final(corpo, formato, "sem ferramenta")

    def _chamada(self, corpo, formato):
        rodada = sum(1 for c in self.recebidos if c is corpo or True)
        cid = f"ccr_{rodada}"
        if formato == "anthropic":
            blocos = [{"type": "text", "text": "vou buscar o log inteiro. "},
                      {"type": "tool_use", "id": cid, "name": rc.NOME, "input": {"hash": H}}]
            if self.misto:
                blocos.append({"type": "tool_use", "id": "b2", "name": "Bash", "input": {"command": "ls"}})
            if corpo.get("stream"):
                return httpx.Response(200, headers={"content-type": "text/event-stream"},
                                      stream=httpx.ByteStream(_sse_anthropic(blocos, "tool_use")))
            return _json(status=200, obj={"id": "m", "type": "message", "role": "assistant", "content": blocos,
                                             "stop_reason": "tool_use"})
        chamadas = [(cid, rc.NOME, json.dumps({"hash": H}))] + ([("b2", "Bash", "{}")] if self.misto else [])
        if corpo.get("stream"):
            return httpx.Response(200, headers={"content-type": "text/event-stream"},
                                  stream=httpx.ByteStream(_sse_openai("vou buscar. ", chamadas, "tool_calls")))
        return _json(status=200, obj={"choices": [{"index": 0, "finish_reason": "tool_calls", "message": {
            "role": "assistant", "content": "vou buscar. ",
            "tool_calls": [{"id": i, "type": "function", "function": {"name": n, "arguments": a}} for i, n, a in chamadas]}}]})

    def _final(self, corpo, formato, texto):
        if formato == "anthropic":
            if corpo.get("stream"):
                return httpx.Response(200, headers={"content-type": "text/event-stream"},
                                      stream=httpx.ByteStream(_sse_anthropic([{"type": "text", "text": texto}], "end_turn")))
            return _json(status=200, obj={"id": "m2", "type": "message", "role": "assistant",
                                             "content": [{"type": "text", "text": texto}], "stop_reason": "end_turn"})
        if corpo.get("stream"):
            return httpx.Response(200, headers={"content-type": "text/event-stream"},
                                  stream=httpx.ByteStream(_sse_openai(texto, [], "stop")))
        return _json(status=200, obj={"choices": [{"index": 0, "finish_reason": "stop",
                                                      "message": {"role": "assistant", "content": texto}}]})


def _cliente(provedor, ligado=True):
    cfg = SimpleNamespace(proxy_min_chars=10**9, proxy_upstream_anthropic="http://p", proxy_upstream_openai="http://p",
                          proxy_ccr=ligado)
    return TestClient(criar_app(cfg, None, cliente_http=httpx.AsyncClient(transport=httpx.MockTransport(provedor))))


def _eventos(sse: bytes) -> list[dict]:
    saida = []
    for q in sse.split(b"\n\n"):
        for linha in q.decode().splitlines():
            if linha.startswith("data:"):
                d = linha[5:].strip()
                saida.append("[DONE]" if d == "[DONE]" else json.loads(d))
    return saida


# ── ponta a ponta ─────────────────────────────────────────────────────────────

def test_anthropic_sem_streaming_resolve_e_o_cliente_ve_so_o_final():
    p = Provedor()
    with _cliente(p) as c:
        r = c.post("/v1/messages", json=_pedido_anthropic(False))
    assert r.status_code == 200
    assert r.json()["content"] == [{"type": "text", "text": "achei 250 linhas"}]
    assert len(p.recebidos) == 2
    tools = p.recebidos[0]["tools"]
    assert [t["name"] for t in tools] == [rc.NOME] and p.recebidos[0]["system"] == "seja breve"
    cont = p.recebidos[1]["messages"]
    assert cont[-2]["role"] == "assistant" and cont[-2]["content"][1]["name"] == rc.NOME
    assert json.loads(cont[-1]["content"][0]["content"]) == {"hash": H, "original_content": ORIGINAL}


def test_anthropic_streaming_emenda_a_continuacao_num_fluxo_so():
    p = Provedor()
    with _cliente(p) as c:
        r = c.post("/v1/messages", json=_pedido_anthropic(True))
    ev = _eventos(r.content)
    tipos = [e["type"] for e in ev]
    assert tipos.count("message_start") == 1 and tipos.count("message_stop") == 1 and tipos[-1] == "message_stop"
    starts = [e for e in ev if e["type"] == "content_block_start"]
    assert [s["index"] for s in starts] == [0, 1], "os indices do cliente tem de seguir 0, 1, ..."
    assert all(s["content_block"]["type"] == "text" for s in starts), "a chamada de recuperacao vazou"
    texto = "".join(e["delta"]["text"] for e in ev if e["type"] == "content_block_delta")
    assert texto == "vou buscar o log inteiro. achei 250 linhas"
    assert [e["delta"]["stop_reason"] for e in ev if e["type"] == "message_delta"] == ["end_turn"]
    assert p.recebidos[1]["stream"] is True


def test_anthropic_streaming_repassa_o_texto_antes_de_a_chamada_chegar():
    """O texto do cliente sai sem esperar o fim do turno: so o bloco da recuperacao fica retido."""
    import asyncio
    eventos = _sse_anthropic([{"type": "text", "text": "abc"}, {"type": "tool_use", "id": "ccr_x", "name": rc.NOME,
                                                               "input": {"hash": H}}], "tool_use")
    corte = eventos.index(b"event: content_block_start", eventos.index(b"text_delta"))
    vistos = []

    async def fonte():
        yield eventos[:corte]
        vistos.append("pausa")
        yield eventos[corte:]

    async def abrir(novo):
        return 500, None

    async def cenario():
        saida = []
        async for b in rc.fluxo_anthropic(fonte(), _pedido_anthropic(True), abrir):
            saida.append((len(vistos), b))
        return saida

    saida = asyncio.run(cenario())
    antes = b"".join(b for n, b in saida if n == 0)
    assert b"text_delta" in antes, "o texto ficou preso esperando o fim do turno"


@pytest.mark.parametrize("stream", [False, True])
def test_openai_chat_resolve(stream):
    p = Provedor()
    with _cliente(p) as c:
        r = c.post("/v1/chat/completions", json=_pedido_openai(stream))
    assert r.status_code == 200
    assert p.recebidos[0]["tools"][0]["function"]["name"] == rc.NOME
    cont = p.recebidos[1]["messages"]
    assert cont[-2]["tool_calls"][0]["function"]["name"] == rc.NOME and cont[-1]["role"] == "tool"
    if not stream:
        assert r.json()["choices"][0]["message"]["content"] == "achei 250 linhas"
        return
    ev = _eventos(r.content)
    assert ev[-1] == "[DONE]" and ev.count("[DONE]") == 1
    texto = "".join((e["choices"][0]["delta"].get("content") or "") for e in ev if e != "[DONE]")
    assert texto == "vou buscar. achei 250 linhas"
    assert not any((e["choices"][0]["delta"].get("tool_calls")) for e in ev if e != "[DONE]"), "a chamada vazou"
    assert [e["choices"][0].get("finish_reason") for e in ev if e != "[DONE]" and e["choices"][0].get("finish_reason")] == ["stop"]


# ── recuos ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("stream", [False, True])
def test_chamada_mista_volta_ao_cliente_sem_continuacao(stream):
    p = Provedor(misto=True)
    with _cliente(p) as c:
        r = c.post("/v1/messages", json=_pedido_anthropic(stream))
    assert len(p.recebidos) == 1
    if not stream:
        nomes = [b.get("name") for b in r.json()["content"] if b["type"] == "tool_use"]
    else:
        nomes = [e["content_block"]["name"] for e in _eventos(r.content) if e["type"] == "content_block_start"
                 and e["content_block"]["type"] == "tool_use"]
        starts = [e["index"] for e in _eventos(r.content) if e["type"] == "content_block_start"]
        assert sorted(starts) == list(range(len(starts))), "indices repetidos ou com buraco no recuo"
    assert sorted(nomes) == sorted([rc.NOME, "Bash"])


@pytest.mark.parametrize("stream", [False, True])
def test_continuacao_que_falha_entrega_o_que_havia(stream):
    p = Provedor(falhar_continuacao=True)
    with _cliente(p) as c:
        r = c.post("/v1/messages", json=_pedido_anthropic(stream))
    assert r.status_code == 200 and len(p.recebidos) == 2
    corpo = r.json()["content"] if not stream else [e["content_block"] for e in _eventos(r.content)
                                                   if e["type"] == "content_block_start"]
    assert any(b.get("name") == rc.NOME for b in corpo)
    if stream:
        tipos = [e["type"] for e in _eventos(r.content)]
        assert tipos.count("message_stop") == 1 and tipos[-1] == "message_stop"


def test_para_em_tres_rodadas():
    p = Provedor(sempre_chama=True)
    with _cliente(p) as c:
        r = c.post("/v1/messages", json=_pedido_anthropic(False))
    assert len(p.recebidos) == 1 + rc.MAX_RODADAS
    assert any(b.get("name") == rc.NOME for b in r.json()["content"])


def test_sem_original_na_guarda_nao_injeta_nada():
    corpo = _pedido_anthropic(False)
    corpo["messages"][2]["content"][0]["content"] = "x [Retrieve more: hash=ffffffffffffffffffffffff]"
    p = Provedor()
    with _cliente(p) as c:
        c.post("/v1/messages", json=corpo)
    assert "tools" not in p.recebidos[0], "anunciou um hash que a guarda nao tem"


def test_desligado_nao_muda_o_pedido():
    p = Provedor()
    with _cliente(p, ligado=False) as c:
        c.post("/v1/messages", json=_pedido_anthropic(False))
    assert len(p.recebidos) == 1 and "tools" not in p.recebidos[0]


def test_ferramenta_ja_presente_nao_e_duplicada_e_as_do_cliente_ficam():
    bash = {"name": "Bash", "description": "roda", "input_schema": {"type": "object"}}
    novo = rc.injetar(rc.injetar(_pedido_anthropic(False, [bash]), "anthropic"), "anthropic")
    assert [t["name"] for t in novo["tools"]] == ["Bash", rc.NOME]


def test_os_tres_ponteiros_sao_reconhecidos():
    corpo = {"messages": [{"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "a", "content": [{"type": "text", "text": f"[Retrieve original: hash={H}]"}]},
        {"type": "text", "text": "<<ccr:aaaaaaaaaaaa 40_rows_offloaded>> e Retrieve more: hash=bbbbbbbbbbbbbbbbbbbbbbbb"}]}]}
    assert rc.hashes(corpo, existe=lambda h: True) == [H, "bbbbbbbbbbbbbbbbbbbbbbbb", "aaaaaaaaaaaa"]


def test_hash_ausente_vira_erro_legivel_para_o_modelo():
    assert json.loads(rc.conteudo_do_resultado("ffffffffffff"))["error"]
    assert json.loads(rc.conteudo_do_resultado(H)) == {"hash": H, "original_content": ORIGINAL}


# ── contra o Headroom original ───────────────────────────────────────────────

ORACULO = r'''
import asyncio, json, sys
sys.path.insert(0, sys.argv[1])
from headroom.proxy.anthropic_wire import AnthropicSSEEnvelope
from headroom.ccr import response_handler as rh
pedido = json.load(sys.stdin)
saida = {"remontagens": [], "continuacoes": []}
for eventos in pedido["streams"]:
    saida["remontagens"].append(AnthropicSSEEnvelope.from_events(eventos).message["content"])
for caso in pedido["continuacoes"]:
    capturado = []
    async def api(msgs, tools):
        capturado.append(msgs)
        return caso["final"]
    h = rh.CCRResponseHandler()
    h._execute_retrieval = lambda chamada: rh.CCRToolResult(tool_call_id=chamada.tool_call_id,
                                                           content=caso["conteudos"][chamada.hash_key], success=True)
    asyncio.run(h.handle_response(caso["resposta"], caso["mensagens"], [], api, caso["provider"]))
    saida["continuacoes"].append(capturado[0] if capturado else None)
json.dump(saida, sys.stdout)
'''


def _sortear_stream(rnd: random.Random) -> tuple[list[dict], list[dict], list[list[dict]]]:
    """Eventos de uma resposta com blocos sorteados: texto, thinking com assinatura, tool_use com JSON
    partido em pedacos de tamanho aleatorio, redacted_thinking."""
    eventos, blocos_ini, deltas = [{"type": "message_start", "message": {"id": "m", "role": "assistant", "content": [],
                                                                       "usage": {"input_tokens": 1}}}], [], []
    for i in range(rnd.randint(1, 5)):
        tipo = rnd.choice(["text", "thinking", "tool_use", "redacted_thinking"])
        if tipo == "text":
            ini, ds = {"type": "text", "text": ""}, [{"type": "text_delta", "text": "".join(rnd.choice("abc é\n") for _ in range(rnd.randint(1, 9)))} for _ in range(rnd.randint(1, 6))]
        elif tipo == "thinking":
            ini = {"type": "thinking", "thinking": ""}
            ds = [{"type": "thinking_delta", "thinking": f"pensa{j} "} for j in range(rnd.randint(1, 4))] + [{"type": "signature_delta", "signature": f"sig{rnd.random()}"}]
        elif tipo == "tool_use":
            ini = {"type": "tool_use", "id": f"t{i}", "name": rnd.choice(["Bash", rc.NOME]), "input": {}}
            js = json.dumps({"hash": H, "n": rnd.randint(0, 99), "lista": [1, "dois", None]})
            cortes = sorted(rnd.sample(range(1, len(js)), rnd.randint(1, 6)))
            pedacos = [js[a:b] for a, b in zip([0] + cortes, cortes + [len(js)])]
            ds = [{"type": "input_json_delta", "partial_json": p} for p in pedacos]
        else:
            ini, ds = {"type": "redacted_thinking", "data": f"cifrado{i}"}, []
        eventos.append({"type": "content_block_start", "index": i, "content_block": ini})
        eventos += [{"type": "content_block_delta", "index": i, "delta": d} for d in ds]
        eventos.append({"type": "content_block_stop", "index": i})
        blocos_ini.append(ini)
        deltas.append(ds)
    eventos += [{"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 3}},
                {"type": "message_stop"}]
    return eventos, blocos_ini, deltas


def _sortear_continuacao(rnd: random.Random, provider: str):
    n = rnd.randint(1, 3)
    ids = [f"call_{rnd.randint(0, 10**6)}_{k}" for k in range(n)]
    hs = [f"{rnd.getrandbits(96):024x}" for _ in range(n)]
    conteudos = {h: json.dumps({"hash": h, "original_content": f"original {h}"}, indent=2) for h in hs}
    mensagens = [{"role": "user", "content": "oi"}]
    if provider == "anthropic":
        conteudo = [{"type": "text", "text": "buscando"}] + [
            {"type": "tool_use", "id": i, "name": "NOME", "input": {"hash": h}} for i, h in zip(ids, hs)]
        resposta = {"content": conteudo, "stop_reason": "tool_use"}
        final = {"content": [{"type": "text", "text": "pronto"}], "stop_reason": "end_turn"}
    else:
        resposta = {"choices": [{"message": {"role": "assistant", "content": "buscando", "tool_calls": [
            {"id": i, "type": "function", "function": {"name": "NOME", "arguments": json.dumps({"hash": h})}} for i, h in zip(ids, hs)]}}]}
        final = {"choices": [{"message": {"role": "assistant", "content": "pronto"}}]}
    return {"provider": provider, "mensagens": mensagens, "resposta": resposta, "final": final, "conteudos": conteudos}


def _com_nome(obj, nome):
    return json.loads(json.dumps(obj).replace('"NOME"', json.dumps(nome)))


@pytest.mark.skipif(not (HEADROOM / "headroom").exists(), reason="copia do Headroom nao esta nesta maquina")
def test_remontagem_e_continuacao_iguais_ao_headroom_original():
    rnd = random.Random(20261123)
    streams = [_sortear_stream(rnd) for _ in range(300)]
    casos = [_sortear_continuacao(rnd, rnd.choice(["anthropic", "openai"])) for _ in range(200)]
    pedido = {"streams": [s[0] for s in streams],
              "continuacoes": [_com_nome(c, "headroom_retrieve") for c in casos]}
    p = subprocess.run([sys.executable, "-c", ORACULO, str(HEADROOM)], input=json.dumps(pedido),
                       capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, p.stderr[-1500:]
    esperado = json.loads(p.stdout)
    # O original precisa de fato fazer algo: remontar blocos e montar continuacoes.
    assert all(esperado["remontagens"]) and all(c is not None for c in esperado["continuacoes"])
    for i, ((_, inis, ds), orig) in enumerate(zip(streams, esperado["remontagens"])):
        assert [rc.remontar_bloco(b, d) for b, d in zip(inis, ds)] == orig, f"stream {i}"
    for i, (caso, orig) in enumerate(zip(casos, esperado["continuacoes"])):
        c = _com_nome(caso, rc.NOME)
        fmt = "anthropic" if c["provider"] == "anthropic" else "openai_chat"
        nossas, outras = rc.chamadas(c["resposta"], fmt)
        assert outras == 0 and len(nossas) == len(c["conteudos"])
        meu = rc.continuacao({"messages": c["mensagens"]}, rc._mensagem_do_assistente(c["resposta"], fmt), fmt,
                             nossas, buscar=lambda h: None)
        # O conteudo do resultado e o que o caso fixou; o resto da estrutura tem de bater.
        for m in meu["messages"]:
            if fmt == "anthropic" and isinstance(m.get("content"), list):
                for b in m["content"]:
                    if b.get("type") == "tool_result":
                        h = next(x["input"]["hash"] for x in c["resposta"]["content"] if x.get("id") == b["tool_use_id"])
                        b["content"] = c["conteudos"][h]
            if m.get("role") == "tool":
                h = next(json.loads(x["function"]["arguments"])["hash"] for x in c["resposta"]["choices"][0]["message"]["tool_calls"]
                         if x["id"] == m["tool_call_id"])
                m["content"] = c["conteudos"][h]
        orig = json.loads(json.dumps(orig).replace('"headroom_retrieve"', json.dumps(rc.NOME)))
        assert meu["messages"] == orig, f"continuacao {i}"


def test_openai_streaming_misto_devolve_as_duas_chamadas_com_indices_validos():
    p = Provedor(misto=True)
    with _cliente(p) as c:
        r = c.post("/v1/chat/completions", json=_pedido_openai(True))
    assert len(p.recebidos) == 1
    ev = [e for e in _eventos(r.content) if e != "[DONE]"]
    chamadas = {}
    for e in ev:
        for t in e["choices"][0]["delta"].get("tool_calls") or []:
            ch = chamadas.setdefault(t["index"], {"nome": None, "args": ""})
            ch["nome"] = (t.get("function") or {}).get("name") or ch["nome"]
            ch["args"] += (t.get("function") or {}).get("arguments") or ""
    assert sorted(chamadas) == [0, 1], "indices de tool_call repetidos ou com buraco"
    assert sorted(c["nome"] for c in chamadas.values()) == sorted(["Bash", rc.NOME])
    assert json.loads([c for c in chamadas.values() if c["nome"] == rc.NOME][0]["args"]) == {"hash": H}
    assert _eventos(r.content)[-1] == "[DONE]"
