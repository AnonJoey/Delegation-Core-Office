"""Dedup entre turnos no proxy (6.3.2): o que o Headroom faz no `ContentRouter`, no proxy do delegation-core.

O teste diferencial roda o `_cross_turn_dedup_messages` ORIGINAL (a copia local do Headroom, com o
nucleo Rust compilado) sobre as mesmas conversas e exige o mesmo resultado; sem a copia, e pulado.
"""

from __future__ import annotations

import copy
import json
import random
import subprocess
import sys
from pathlib import Path

import pytest

from delegation_core.proxy import dedup
from delegation_core.proxy.reescrita import reescrever

HEADROOM = Path.home() / "Projects" / "headroom"
NUCLEO = HEADROOM / "target" / "release" / "lib_core.so"

ARQUIVO = "".join(f"def funcao_{i}(x):\n    valor = x * {i} + calcula_mais_alguma_coisa(x)\n    return valor\n\n" for i in range(12))


def _numerado(texto: str, deslocamento: int = 0) -> str:
    return "\n".join(f"{i + 1 + deslocamento}:{l}" for i, l in enumerate(texto.split("\n")))


def _conversa(*saidas, nomes=None, cache=()):
    msgs = [{"role": "user", "content": "leia o arquivo"}]
    for i, s in enumerate(saidas):
        nome = (nomes or {}).get(i, "Bash")
        msgs.append({"role": "assistant", "content": [{"type": "tool_use", "id": f"t{i}", "name": nome, "input": {}}]})
        bloco = {"type": "tool_result", "tool_use_id": f"t{i}", "content": s}
        if i in cache:
            bloco["cache_control"] = {"type": "ephemeral"}
        msgs.append({"role": "user", "content": [bloco]})
    return msgs


def _resultados(msgs):
    return [b["content"] for m in msgs if isinstance(m.get("content"), list) for b in m["content"]
            if isinstance(b, dict) and b.get("type") == "tool_result"]


# ── comportamento ────────────────────────────────────────────────────────────

def test_a_segunda_leitura_igual_vira_ponteiro_e_a_primeira_fica():
    msgs = _conversa(ARQUIVO, "sem relacao\n", ARQUIVO)
    novas, n, chars = dedup.dedup_mensagens(msgs)
    r = _resultados(novas)
    assert n == 1 and chars > 0
    assert r[0] == ARQUIVO and r[1] == "sem relacao\n"
    assert r[2].startswith("[↑") and "same as msg 2" in r[2] and len(r[2]) < len(ARQUIVO) / 10


def test_nao_mexe_na_entrada():
    msgs = _conversa(ARQUIVO, ARQUIVO)
    copia = copy.deepcopy(msgs)
    dedup.dedup_mensagens(msgs)
    assert msgs == copia


def test_releitura_depois_de_uma_edicao_que_deslocou_as_linhas_ainda_dobra():
    msgs = _conversa(_numerado(ARQUIVO), _numerado(ARQUIVO, 3))
    novas, n, _ = dedup.dedup_mensagens(msgs)
    assert n == 1 and "+3L" in _resultados(novas)[1]


def test_resultado_protegido_serve_de_referencia_e_nao_e_reescrito():
    for nome in ("WebFetch", "view", "mcp__srv__web_fetch", "mcp_srv_WebSearch", "recall_output",
                 "mcp__delegation-core__recall_output"):
        msgs = _conversa(ARQUIVO, ARQUIVO, nomes={1: nome})
        novas, n, _ = dedup.dedup_mensagens(msgs)
        assert n == 0 and _resultados(novas)[1] == ARQUIVO, nome
    # Protegido como PRIMEIRO bloco ainda e referencia para o segundo.
    novas, n, _ = dedup.dedup_mensagens(_conversa(ARQUIVO, ARQUIVO, nomes={0: "WebFetch"}))
    assert n == 1 and _resultados(novas)[0] == ARQUIVO


def test_cache_control_nunca_e_reescrito():
    novas, n, _ = dedup.dedup_mensagens(_conversa(ARQUIVO, ARQUIVO, cache=(1,)))
    assert n == 0 and _resultados(novas)[1] == ARQUIVO


def test_conteudo_em_lista_com_um_so_bloco_de_texto():
    msgs = _conversa(ARQUIVO, ARQUIVO)
    msgs[4]["content"][0]["content"] = [{"type": "text", "text": ARQUIVO}]
    novas, n, _ = dedup.dedup_mensagens(msgs)
    sub = novas[4]["content"][0]["content"]
    assert n == 1 and sub[0]["type"] == "text" and sub[0]["text"].startswith("[↑")
    # Dois blocos de texto: fica como esta, para continuar trivialmente sem perda.
    msgs[4]["content"][0]["content"] = [{"type": "text", "text": ARQUIVO}, {"type": "text", "text": "mais"}]
    assert dedup.dedup_mensagens(msgs)[1] == 0


def test_openai_chat_mensagens_tool():
    msgs = [{"role": "user", "content": "x"},
            {"role": "assistant", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "bash", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "c1", "content": ARQUIVO},
            {"role": "assistant", "tool_calls": [{"id": "c2", "type": "function", "function": {"name": "bash", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "c2", "content": ARQUIVO},
            {"role": "user", "content": ARQUIVO}]   # prosa do usuario nunca dobra
    novas, n, _ = dedup.dedup_mensagens(msgs)
    assert n == 1 and novas[2]["content"] == ARQUIVO and novas[4]["content"].startswith("[↑") and novas[5]["content"] == ARQUIVO


def test_so_um_bloco_ou_nenhum_repetido_devolve_o_mesmo_objeto():
    um = _conversa(ARQUIVO)
    assert dedup.dedup_mensagens(um)[0] is um
    dois = _conversa(ARQUIVO, "outra coisa inteira\n" * 20)
    assert dedup.dedup_mensagens(dois)[0] is dois


def test_mensagem_malformada_nao_levanta():
    for ruim in ([None, 3, "x"], [{"role": "user", "content": [None, {"type": "tool_result"}]}],
                 [{"role": "assistant", "content": 5, "tool_calls": [None]}, {"role": "tool"}]):
        assert dedup.dedup_mensagens(ruim)[1] == 0


def test_acrescentar_um_turno_nao_muda_os_turnos_anteriores():
    """A garantia de cache: o prefixo reescrito e o mesmo com ou sem o turno seguinte."""
    ate_3 = _conversa(ARQUIVO, "meio\n" * 30, ARQUIVO)
    ate_4 = ate_3 + _conversa(ARQUIVO)[1:]
    a = _resultados(dedup.dedup_mensagens(ate_3)[0])
    b = _resultados(dedup.dedup_mensagens(ate_4)[0])
    assert b[:len(a)] == a and b[3].startswith("[↑")


# ── pelo proxy ───────────────────────────────────────────────────────────────

def test_reescrever_so_dobra_com_a_flag_ligada():
    corpo = {"messages": _conversa(ARQUIVO, ARQUIVO)}
    sem, rel_sem = reescrever("/v1/messages", copy.deepcopy(corpo), 10**9)
    assert _resultados(sem["messages"]) == [ARQUIVO, ARQUIVO] and rel_sem.trechos_dedup == 0
    com, rel_com = reescrever("/v1/messages", copy.deepcopy(corpo), 10**9, dedup=True)
    assert rel_com.trechos_dedup == 1 and _resultados(com["messages"])[1].startswith("[↑")
    assert rel_com.chars_depois < rel_com.chars_antes
    # OpenAI Responses nao e coberto.
    resp, rel = reescrever("/v1/responses", {"input": []}, 10**9, dedup=True)
    assert rel.trechos_dedup == 0


def test_o_servidor_manda_o_corpo_dobrado_quando_a_flag_esta_ligada(tmp_path):
    from types import SimpleNamespace

    import httpx
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    from delegation_core.proxy.servidor import criar_app
    from tests.test_proxy import _porta, _subir

    recebidos = []

    async def provedor(req):
        recebidos.append(json.loads(await req.body()))
        return JSONResponse({"ok": True})

    p_prov, p_proxy = _porta(), _porta()
    prov = _subir(Starlette(routes=[Route("/{c:path}", provedor, methods=["POST"])]), p_prov)
    try:
        for flag in (False, True):
            cfg = SimpleNamespace(proxy_min_chars=10**9, proxy_cross_turn_dedup=flag,
                                  proxy_upstream_anthropic=f"http://127.0.0.1:{p_prov}",
                                  proxy_upstream_openai=f"http://127.0.0.1:{p_prov}")
            proxy = _subir(criar_app(cfg), p_proxy)
            try:
                httpx.post(f"http://127.0.0.1:{p_proxy}/v1/messages", json={"messages": _conversa(ARQUIVO, ARQUIVO)}, timeout=30)
            finally:
                proxy.should_exit = True
            p_proxy = _porta()
    finally:
        prov.should_exit = True
    sem, com = recebidos
    assert _resultados(sem["messages"]) == [ARQUIVO, ARQUIVO]
    assert _resultados(com["messages"])[1].startswith("[↑")


# ── contra o Headroom original ───────────────────────────────────────────────

ORACULO = r'''
import importlib.util, json, sys
sys.path.insert(0, sys.argv[1])
spec = importlib.util.spec_from_file_location("headroom._core", sys.argv[2])
core = importlib.util.module_from_spec(spec)
sys.modules["headroom._core"] = core
spec.loader.exec_module(core)
from headroom.transforms.content_router import ContentRouter
r = ContentRouter()
r._cross_turn_dedup_enabled = True
saida = []
for msgs in json.load(sys.stdin):
    saida.append(r._cross_turn_dedup_messages(msgs, 0, [], None))
json.dump(saida, sys.stdout)
'''


def _sortear(r: random.Random):
    arquivos = [ARQUIVO.replace("funcao_", f"f{k}_") for k in range(3)]
    ferramentas = ["Bash", "Bash", "Bash", "Grep", "WebFetch", "view", "mcp__srv__web_search", "recall_outputx"]
    saidas, nomes, cache = [], {}, set()
    for i in range(r.randint(2, 7)):
        base = r.choice(arquivos)
        linhas = base.split("\n")
        a = r.randint(0, 4)
        b = len(linhas) - r.randint(0, 4)
        trecho = "\n".join(linhas[a:b]) if r.random() < .6 else base
        if r.random() < .4:
            trecho = _numerado(trecho, r.choice([0, 0, 2, 5]))
        if r.random() < .25:
            trecho += "\n" + "linha extra unica numero %d para variar o bloco\n" % r.randint(0, 999)
        saidas.append(trecho if r.random() < .9 else "curto")
        nomes[i] = r.choice(ferramentas)
        if r.random() < .15:
            cache.add(i)
    msgs = _conversa(*saidas, nomes=nomes, cache=cache)
    if r.random() < .3:   # um resultado como lista com um bloco de texto
        k = r.choice([j for j, m in enumerate(msgs) if m["role"] == "user" and isinstance(m["content"], list)] or [None])
        if k is not None:
            blk = msgs[k]["content"][0]
            blk["content"] = [{"type": "text", "text": blk["content"]}]
    return msgs


@pytest.mark.skipif(not NUCLEO.exists() or not (HEADROOM / "headroom").exists(), reason="copia compilada do Headroom nao esta nesta maquina")
def test_igual_ao_headroom_original_em_conversas_sorteadas():
    r = random.Random(20261016)
    conversas = [_sortear(r) for _ in range(250)]
    p = subprocess.run([sys.executable, "-c", ORACULO, str(HEADROOM), str(NUCLEO)], input=json.dumps(conversas),
                       capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, p.stderr[-800:]
    esperado = json.loads(p.stdout)
    # O original engole qualquer excecao e devolve a entrada: um oraculo mal montado "nao dobra nada".
    # Por isso se confere que ELE dobra, e nao so que o porte concorda com ele.
    assert sum(o != m for m, o in zip(conversas, esperado)) > 40, "o Headroom original nao dobrou quase nada"
    dobradas = 0
    for i, (msgs, orig) in enumerate(zip(conversas, esperado)):
        obtido = dedup.dedup_mensagens(copy.deepcopy(msgs))[0]
        assert obtido == orig, f"conversa {i} difere do Headroom"
        dobradas += obtido != msgs
    assert dobradas > 40, f"so {dobradas} de 250 conversas dobraram: o teste nao exercita o dedup"
