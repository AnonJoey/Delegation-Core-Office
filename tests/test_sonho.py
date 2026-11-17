"""Pacote sonho: registro de recordacao e o julgamento de contradicao com citacao conferida."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from delegation_core.sonho import RegistroDeRecordacao
from delegation_core.sonho import contradicao as c

PACOTE = Path(__file__).resolve().parents[1] / "src" / "delegation_core" / "sonho"
DIA = 86400.0


@pytest.fixture
def reg(tmp_path):
    r = RegistroDeRecordacao(tmp_path / "rec.sqlite3")
    yield r
    r.fechar()


# ── recordacao ──────────────────────────────────────────────────────────────

def test_mais_lembradas_exige_consultas_diferentes(reg):
    for _ in range(5):
        reg.registrar("a mesma pergunta", ["x.md"], em=1000)
    assert reg.mais_lembradas(agora=1000) == []
    reg.registrar("outra pergunta", ["x.md"], em=1000)
    reg.registrar("terceira", ["x.md"], em=1000)
    r = reg.mais_lembradas(agora=1000)
    assert r[0]["caminho"] == "x.md" and r[0]["consultas_unicas"] == 3 and r[0]["recordacoes"] == 7


def test_consulta_igual_ignora_caixa_e_espaco(reg):
    reg.registrar("Onde  fica o Vault", ["x.md"], em=1)
    reg.registrar("onde fica o vault", ["x.md"], em=1)
    reg.registrar("outra", ["x.md"], em=1)
    assert reg.mais_lembradas(min_consultas_unicas=3, agora=1) == []


def test_so_conta_quem_veio_no_topo(reg):
    for q in ("a", "b", "c"):
        reg.registrar(q, ["p1.md", "p2.md", "p3.md", "fundo.md"], em=1)
    assert "fundo.md" not in [d["caminho"] for d in reg.mais_lembradas(topo=3, agora=1)]


def test_meia_vida_pesa_o_recente(reg):
    for q in ("a", "b", "c"):
        reg.registrar(q, ["velha.md"], em=0)
        reg.registrar(q, ["nova.md"], em=28 * DIA)
    r = {d["caminho"]: d["pontos"] for d in reg.mais_lembradas(agora=28 * DIA, meia_vida_dias=14)}
    assert r["nova.md"] == pytest.approx(3.0) and r["velha.md"] == pytest.approx(0.75)


def test_desde_corta_o_passado(reg):
    for q in ("a", "b", "c"):
        reg.registrar(q, ["x.md"], em=10)
    assert reg.mais_lembradas(desde=20, agora=30) == []


def test_nunca_lembradas(reg):
    reg.registrar("q", ["a.md"], em=5)
    assert reg.nunca_lembradas(["a.md", "b.md", "c.md"]) == ["b.md", "c.md"]
    assert reg.nunca_lembradas(["a.md"], desde=10) == ["a.md"]


def test_lacunas_so_as_repetidas_e_sem_boa_resposta(reg):
    reg.registrar("como configurar o onedrive da soteria", [], confianca="low", em=1)
    reg.registrar("como configurar o onedrive da soteria", ["x.md"], confianca="low", melhor=0.51, em=2)
    reg.registrar("pergunta unica", [], confianca="low", em=3)
    reg.registrar("tem resposta", [], confianca="low", em=4)
    reg.registrar("tem resposta", ["y.md"], confianca="high", em=5)
    lac = reg.lacunas()
    assert [l["consulta"] for l in lac] == ["como configurar o onedrive da soteria"]
    assert lac[0]["vezes"] == 2 and lac[0]["melhor_similaridade"] == 0.51


def test_consulta_longa_e_cortada(reg):
    reg.registrar("x" * 1000, ["a.md"])
    reg.registrar("x" * 1000, ["a.md"])
    assert len(reg.lacunas()[0]["consulta"]) == 300


def test_estatisticas(reg):
    reg.registrar("a", ["x.md", "y.md"])
    reg.registrar("a", ["x.md"])
    assert reg.estatisticas() == {"consultas": 2, "consultas_unicas": 1, "notas_ja_devolvidas": 2}


# ── contradicao ─────────────────────────────────────────────────────────────

A = "O embed_device fica em cpu por config, e o drop-in cpu-embeddings.conf foi removido em 26/09."
B = "Decisao: colocar CUDA_VISIBLE_DEVICES vazio no drop-in cpu-embeddings.conf para tirar o BGE da GPU."


def _resp(rel, cb="CUDA_VISIBLE_DEVICES vazio no drop-in", ca="o drop-in cpu-embeddings.conf foi removido", conf=0.9):
    import json
    return json.dumps({"relation": rel, "claim_in_B": cb, "claim_in_A": ca, "confidence": conf})


def test_atualizacao_com_citacoes_reais_e_achado():
    v = c.julgar(lambda s, p: _resp("updates"), "A", "2026-09-26", A, "B", "2026-09-02", B)
    assert v.achado and v.relacao == "updates" and v.confianca == 0.9


def test_citacao_inventada_derruba_o_achado():
    v = c.julgar(lambda s, p: _resp("contradicts", cb="o BGE deve rodar sempre na GPU"),
                 "A", "d", A, "B", "d", B)
    assert not v.achado and any("claim_in_B" in p for p in v.problemas)


def test_citacao_de_a_tambem_e_conferida():
    v = c.julgar(lambda s, p: _resp("updates", ca="a placa foi trocada por outra"), "A", "d", A, "B", "d", B)
    assert not v.achado and any("claim_in_A" in p for p in v.problemas)


def test_repete_e_complementa_nao_sao_achado_mesmo_com_citacao():
    for rel in ("repeats", "complements", "unrelated"):
        assert not c.julgar(lambda s, p, r=rel: _resp(r), "A", "d", A, "B", "d", B).achado


def test_citacao_ignora_acento_caixa_e_markdown():
    assert c.citacao_existe("contencao de GPU entre o BGE", "A **Contenção** de `GPU` entre o BGE e o llama")


def test_citacao_curta_demais_nao_prova():
    assert not c.citacao_existe("o BGE", "o BGE roda na GPU")


def test_citacao_com_reticencias_confere_pedacos_em_ordem():
    t = "primeiro o daemon carrega o BGE, depois sobe o llama inteiro na placa"
    assert c.citacao_existe("o daemon carrega o BGE ... sobe o llama inteiro", t)
    assert not c.citacao_existe("sobe o llama inteiro ... o daemon carrega o BGE", t)


def test_citacao_costurada_de_pedacos_reais_confere():
    """Caso real do primeiro sonho: o modelo juntou duas frases da nota numa so."""
    t = ("O BGE-m3 foi movido para CPU por drop-in do systemd. Outra frase no meio. "
         "O motivo: os dois juntos nao cabem nos 16 GB da placa.")
    assert c.citacao_existe("BGE-m3 foi movido para CPU por drop-in do systemd, "
                            "os dois juntos nao cabem nos 16 GB da placa", t)


def test_citacao_com_trecho_inventado_nao_confere():
    """O outro caso real: `(-ngl 99)` nao existe na nota, e o resto sim."""
    t = "o llama-server passou a rodar na GPU depois que o drop-in saiu"
    assert not c.citacao_existe("o llama-server passou a rodar com offload total na GPU (-ngl 99)", t)


def test_interpretar_tolera_cerca_e_prosa():
    bruto = 'Aqui esta:\n```json\n{"relation": "updates", "claim_in_B": "x", "claim_in_A": "y", "confidence": 2}\n```'
    v = c.interpretar(bruto)
    assert v.relacao == "updates" and v.confianca == 1.0


def test_interpretar_sem_json_ou_relacao_estranha():
    assert c.interpretar("nao sei").relacao == "invalido"
    assert c.interpretar('{"relation": "talvez"}').relacao == "invalido"
    assert c.interpretar('{"relation": "repeats", "confidence": "alta"}').confianca == 0.0


def test_primeiro_json_pula_chave_quebrada():
    assert c._primeiro_json('{quebrado} e depois {"relation": "repeats"}') == {"relation": "repeats"}


def test_prompt_corta_as_notas():
    p = c.montar_prompt("ta", "d1", "a" * 5000, "tb", "d2", "b" * 5000, max_chars=100)
    assert p.count("a") < 200 and "NOTE B (d2): tb" in p


def test_pacote_nao_importa_o_nucleo():
    proibidos = []
    for arq in PACOTE.glob("*.py"):
        for no in ast.walk(ast.parse(arq.read_text())):
            if isinstance(no, ast.ImportFrom) and (no.level >= 2 or (no.module or "").startswith("delegation_core")):
                proibidos.append(f"{arq.name}: {no.module}")
    assert proibidos == []


# ── voto implicito: abrir um resultado ──────────────────────────────────────

def test_abertura_liga_a_busca_recente_e_a_posicao(reg):
    reg.registrar("gpu", ["a.md", "b.md", "c.md"], em=1000)
    assert reg.registrar_abertura("b.md", em=1100) == {"consulta": 1, "posicao": 2}


def test_abertura_fora_da_janela_ou_sem_busca_fica_solta(reg):
    reg.registrar("gpu", ["a.md"], em=1000)
    assert reg.registrar_abertura("a.md", janela_s=60, em=2000) == {"consulta": None, "posicao": None}
    assert reg.registrar_abertura("nunca.md", em=1001) == {"consulta": None, "posicao": None}
    assert reg.aberturas_sem_busca() == 2


def test_abertura_pega_a_busca_mais_recente(reg):
    reg.registrar("q1", ["x.md", "a.md"], em=1000)
    reg.registrar("q2", ["a.md"], em=1050)
    assert reg.registrar_abertura("a.md", em=1100)["posicao"] == 1


def test_taxa_de_abertura_por_posicao(reg):
    for i in range(4):
        reg.registrar(f"q{i}", ["p1.md", "p2.md"], em=1000 + i)
    for i in range(3):
        reg.registrar_abertura("p1.md", em=1010 + i)
    reg.registrar_abertura("p2.md", em=1020)
    r = {d["posicao"]: d for d in reg.aberturas_por_posicao()}
    assert r[1] == {"posicao": 1, "devolvidas": 4, "abertas": 3, "taxa": 0.75}
    assert r[2]["abertas"] == 1 and r[2]["taxa"] == 0.25
