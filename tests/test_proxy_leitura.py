"""Ciclo de vida do Read no proxy (6.3.2, 2/2): Read de arquivo editado depois vira marcador com a chave do original."""

from __future__ import annotations

import copy
import json
import random
import subprocess
import sys
from pathlib import Path

import pytest

from delegation_core.compressao.ccr import Guarda
from delegation_core.proxy import leitura
from delegation_core.proxy.reescrita import reescrever

HEADROOM = Path.home() / "Projects" / "headroom"
CONTEUDO = "".join(f"linha {i} do arquivo com algum texto para passar do minimo de bytes\n" for i in range(30))


def _chamada(i, nome, caminho, **extra):
    return {"role": "assistant", "content": [{"type": "tool_use", "id": f"c{i}", "name": nome,
                                              "input": {"file_path": caminho, **extra}}]}


def _resultado(i, texto):
    return {"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"c{i}", "content": texto}]}


def _roteiro(*passos):
    """passos: (nome, caminho, resultado[, extra])"""
    msgs = [{"role": "user", "content": "trabalhe"}]
    for i, (nome, caminho, saida, *extra) in enumerate(passos):
        msgs += [_chamada(i, nome, caminho, **(extra[0] if extra else {})), _resultado(i, saida)]
    return msgs


def _saida(msgs, i):
    return msgs[2 + 2 * i]["content"][0]["content"]


@pytest.fixture(autouse=True)
def _guarda_isolada(tmp_path, monkeypatch):
    from delegation_core import config
    from delegation_core.filtros_saida import execucao
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    execucao._CON.clear()


def test_read_de_arquivo_editado_depois_vira_marcador_e_o_original_se_recupera():
    msgs = _roteiro(("Read", "/p/a.py", CONTEUDO), ("Edit", "/p/a.py", "ok"))
    r = leitura.aplicar(msgs)
    marcador = _saida(r.messages, 0)
    assert marcador.startswith("[Read content stale: /p/a.py") and "Retrieve original: hash=" in marcador
    chave = marcador.rsplit("hash=", 1)[1].rstrip("]")
    assert len(chave) == 24 and Guarda().get(chave) == CONTEUDO       # o recall_output devolve o original
    assert _saida(r.messages, 1) == "ok"
    assert _saida(msgs, 0) == CONTEUDO                                 # a entrada nao foi tocada


def test_a_chave_e_a_do_conteudo_como_no_original():
    import hashlib
    r = leitura.aplicar(_roteiro(("Read", "/p/a.py", CONTEUDO), ("Write", "/p/a.py", "ok")))
    assert _saida(r.messages, 0).endswith(f"hash={hashlib.sha256(CONTEUDO.encode()).hexdigest()[:24]}]")


def test_o_que_nao_deve_mudar():
    # leitura fresca (nenhuma edicao depois)
    assert _saida(leitura.aplicar(_roteiro(("Read", "/p/a.py", CONTEUDO))).messages, 0) == CONTEUDO
    # edicao ANTES da leitura
    assert _saida(leitura.aplicar(_roteiro(("Edit", "/p/a.py", "ok"), ("Read", "/p/a.py", CONTEUDO))).messages, 1) == CONTEUDO
    # outro arquivo
    assert _saida(leitura.aplicar(_roteiro(("Read", "/p/a.py", CONTEUDO), ("Edit", "/p/b.py", "ok"))).messages, 0) == CONTEUDO
    # menor que 512 bytes
    assert _saida(leitura.aplicar(_roteiro(("Read", "/p/a.py", "curto"), ("Edit", "/p/a.py", "ok"))).messages, 0) == "curto"
    # ferramenta que nao e Read
    assert _saida(leitura.aplicar(_roteiro(("Bash", "/p/a.py", CONTEUDO), ("Edit", "/p/a.py", "ok"))).messages, 0) == CONTEUDO
    # resultado em lista de blocos: o original so trata texto direto
    msgs = _roteiro(("Read", "/p/a.py", CONTEUDO), ("Edit", "/p/a.py", "ok"))
    msgs[2]["content"][0]["content"] = [{"type": "text", "text": CONTEUDO}]
    assert leitura.aplicar(msgs).messages[2]["content"][0]["content"] == [{"type": "text", "text": CONTEUDO}]


def test_read_refeito_inteiro_so_vira_marcador_com_a_flag():
    msgs = _roteiro(("Read", "/p/a.py", CONTEUDO), ("Read", "/p/a.py", CONTEUDO))
    assert _saida(leitura.aplicar(msgs).messages, 0) == CONTEUDO
    r = leitura.aplicar(msgs, superseded=True)
    assert _saida(r.messages, 0).startswith("[Read content superseded: /p/a.py") and _saida(r.messages, 1) == CONTEUDO
    # Read parcial refeito noutra faixa nao cobre o anterior.
    parciais = _roteiro(("Read", "/p/a.py", CONTEUDO, {"offset": 0, "limit": 50}), ("Read", "/p/a.py", CONTEUDO, {"offset": 100, "limit": 50}))
    assert _saida(leitura.aplicar(parciais, superseded=True).messages, 0) == CONTEUDO


def test_openai_chat_role_tool():
    msgs = [{"role": "user", "content": "x"},
            {"role": "assistant", "tool_calls": [{"id": "r", "type": "function", "function": {"name": "Read", "arguments": json.dumps({"file_path": "/p/a.py"})}}]},
            {"role": "tool", "tool_call_id": "r", "content": CONTEUDO},
            {"role": "assistant", "tool_calls": [{"id": "e", "type": "function", "function": {"name": "Edit", "arguments": json.dumps({"file_path": "/p/a.py"})}}]},
            {"role": "tool", "tool_call_id": "e", "content": "ok"}]
    r = leitura.aplicar(msgs)
    assert r.messages[2]["content"].startswith("[Read content stale: /p/a.py") and r.messages[4]["content"] == "ok"


def test_mensagem_malformada_nao_levanta():
    for ruim in ([None, 3], [{"role": "assistant", "content": [None]}, {"role": "tool"}], "texto"):
        assert leitura.aplicar(ruim).messages is not None


# ── pelo proxy ───────────────────────────────────────────────────────────────

def test_reescrever_so_age_com_a_flag_ligada():
    corpo = {"messages": _roteiro(("Read", "/p/a.py", CONTEUDO), ("Edit", "/p/a.py", "ok"))}
    sem, rel = reescrever("/v1/messages", copy.deepcopy(corpo), 10**9)
    assert _saida(sem["messages"], 0) == CONTEUDO and rel.leituras_obsoletas == 0
    com, rel = reescrever("/v1/messages", copy.deepcopy(corpo), 10**9, leitura=True)
    assert rel.leituras_obsoletas == 1 and _saida(com["messages"], 0).startswith("[Read content stale")
    assert rel.chars_antes >= len(CONTEUDO) - 400      # o livro conta o que o Read era
    # So Anthropic e OpenAI Chat.
    resp, rel = reescrever("/v1/responses", {"input": []}, 10**9, leitura=True)
    assert rel.leituras_obsoletas == 0


def test_leitura_e_dedup_juntos():
    arquivo = "".join(f"def f{i}(x):\n    valor = x * {i} + calcula_mais_alguma_coisa(x)\n    return valor\n\n" for i in range(12))
    corpo = {"messages": _roteiro(("Read", "/p/a.py", CONTEUDO), ("Edit", "/p/a.py", "ok"),
                                  ("Bash", "/p/b.py", arquivo), ("Bash", "/p/c.py", arquivo))}
    novo, rel = reescrever("/v1/messages", corpo, 10**9, dedup=True, leitura=True)
    assert rel.leituras_obsoletas == 1 and rel.trechos_dedup == 1
    assert _saida(novo["messages"], 0).startswith("[Read content stale") and _saida(novo["messages"], 3).startswith("[↑")
    assert _saida(novo["messages"], 2) == arquivo


# ── contra o Headroom original ───────────────────────────────────────────────

ORACULO = r'''
import json, sys
sys.path.insert(0, sys.argv[1])
from headroom.transforms.read_lifecycle import ReadLifecycleManager
from headroom.config import ReadLifecycleConfig
sup = sys.argv[2] == "1"
saida = []
for msgs in json.load(sys.stdin):
    r = ReadLifecycleManager(ReadLifecycleConfig(enabled=True, compress_superseded=sup), None).apply(msgs)
    saida.append(r.messages)
json.dump(saida, sys.stdout)
'''


def _sortear(rnd: random.Random):
    arquivos = ["/p/a.py", "/p/b.py", "/p/c.py"]
    passos = []
    for _ in range(rnd.randint(2, 8)):
        nome = rnd.choice(["Read", "Read", "Read", "Edit", "Write", "Bash", "read"])
        caminho = rnd.choice(arquivos)
        saida = CONTEUDO if rnd.random() < .8 else "curto"
        extra = {}
        if nome in ("Read", "read") and rnd.random() < .3:
            extra = {"offset": rnd.choice([0, 100, 200]), "limit": rnd.choice([50, 100, 300])}
        passos.append((nome, caminho, saida, extra))
    return _roteiro(*passos)


@pytest.mark.skipif(not (HEADROOM / "headroom").exists(), reason="copia do Headroom nao esta nesta maquina")
@pytest.mark.parametrize("superseded", [False, True])
def test_igual_ao_headroom_original_em_conversas_sorteadas(superseded):
    rnd = random.Random(20261016 + superseded)
    conversas = [_sortear(rnd) for _ in range(200)]
    p = subprocess.run([sys.executable, "-c", ORACULO, str(HEADROOM), "1" if superseded else "0"],
                       input=json.dumps(conversas), capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, p.stderr[-800:]
    esperado = json.loads(p.stdout)
    assert sum(o != m for m, o in zip(conversas, esperado)) > 40, "o original nao trocou quase nada"
    for i, (msgs, orig) in enumerate(zip(conversas, esperado)):
        assert leitura.aplicar(copy.deepcopy(msgs), superseded=superseded).messages == orig, f"conversa {i}"
