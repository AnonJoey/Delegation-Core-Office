"""Autoridade na busca: o fator por tipo, camada, fixacao e etiqueta, e o roteamento de pergunta de sessao.

A paridade com o ai-memory compilado e conferida por `scripts/paridade_ai_memory.py`; aqui ficam
os exemplos escritos a mao.
"""

from __future__ import annotations

import pytest

from delegation_core.ranqueamento.autoridade import (
    PISO,
    TETO,
    autoridade_da_nota,
    eh_pergunta_de_sessao,
    etiquetas_de,
    limite_de_candidatos,
    multiplicar_posto,
    normalizar_etiqueta,
)


def _fator(tipo, camada, fixada=False, fm=None, caminho="x.md"):
    return autoridade_da_nota(caminho, tipo, camada, fixada, fm).fator


def test_decisao_semantica_ganha_e_sessao_episodica_perde():
    assert _fator("decision", "semantic") == pytest.approx(1.25)
    assert _fator("session", "episodic") == pytest.approx(0.77)
    assert _fator("outro", "") == 1.0


def test_fixada_soma_e_o_fator_nunca_sai_da_faixa():
    assert _fator("procedure", "procedural", fixada=True) == pytest.approx(1.30)
    assert _fator("decision", "semantic", True, {"tags": ["canonical", "active"]}) == TETO
    assert PISO <= _fator("session", "episodic", fm={"tags": ["superseded"]}) <= TETO


def test_etiqueta_negativa_limita_e_a_mais_forte_vence():
    assert _fator("rule", "semantic", fm={"tags": ["do-not-answer-from"]}) == 0.55
    assert _fator("rule", "semantic", fm={"tags": ["test-fixture"]}) == 0.55
    assert _fator("rule", "semantic", fm={"tags": ["superseded"]}) == 0.65
    assert _fator("rule", "semantic", fm={"tags": ["historical"]}) == 0.80
    # canonical sobe, mas historical ainda limita
    assert _fator("decision", "semantic", fm={"tags": ["canonical", "historical"]}) == 0.80
    # a mais restritiva ganha quando vem mais de uma
    assert _fator("rule", "semantic", fm={"tags": ["historical", "superseded"]}) == 0.65


def test_etiqueta_ignora_caixa_espacos_e_sublinhado():
    assert normalizar_etiqueta(" Do_Not_Answer_From ") == "do-not-answer-from"
    assert etiquetas_de({"tags": ["Canonical", " active "]}) == ["canonical", "active"]
    assert _fator("rule", "semantic", fm={"tags": ["SOURCE_OF_TRUTH"]}) == pytest.approx(1.15 + 0.10 + 0.20)


def test_frontmatter_que_nao_e_dicionario_ou_tags_que_nao_sao_lista():
    for fm in (None, [], "texto", 7, {"tags": "canonical"}, {"tags": None}, {}):
        assert etiquetas_de(fm) == []
    assert etiquetas_de({"tags": ["x", 1, None]}) == ["x"]


def test_pastas_de_baixa_autoridade():
    assert _fator("", "", caminho="_lint/x.md") == pytest.approx(0.80)
    assert _fator("session", "episodic", caminho="_lint/x.md") == pytest.approx(0.57)  # o menor fator sem etiqueta
    assert _fator("", "", caminho="investigations/x.md") == pytest.approx(0.95)


def test_pergunta_de_sessao_devolve_a_penalidade_e_um_bonus():
    a = autoridade_da_nota("S/x.md", "session", "episodic", False)
    assert a.fator_para(False, 0.25) == pytest.approx(0.77)
    assert a.fator_para(True, 0.25) == pytest.approx(1.25)
    assert autoridade_da_nota("D/x.md", "decision", "semantic", False).fator_para(True, 0.25) == pytest.approx(1.25)


def test_multiplicar_posto_melhora_o_posto_nas_duas_convencoes():
    assert multiplicar_posto(-0.8, 1.5) < -0.8  # RRF negado: mais negativo e melhor
    assert multiplicar_posto(3.0, 1.5) < 3.0    # bm25 bruto: menor e melhor
    assert multiplicar_posto(3.0, 0.55) > 3.0   # autoridade baixa piora
    assert multiplicar_posto(0.0, 1.5) == 0.0


def test_janela_de_candidatos():
    assert [limite_de_candidatos(n) for n in (0, 1, 5, 10, 100, 500)] == [0, 20, 20, 40, 400, 800]


@pytest.mark.parametrize("pergunta", [
    "o que fizemos na última sessão", "o que fizemos na ultima sessao", "onde paramos ontem", "lembre a decisão anterior",
    "what did we decide last time about the reranker", "yesterday's session on the spool bug", "上次排查 Caddy 配置的会话完成了吗",
    "WHEN WE changed the port", "Previously, the daemon crashed",
])
def test_pergunta_de_sessao_reconhecida(pergunta):
    assert eh_pergunta_de_sessao(pergunta)


@pytest.mark.parametrize("pergunta", [
    "known issue with snow rendering", "unknown snowfall", "git commit unable to auto-detect email", "user_sessions 异常会话 登录失败",
    "qual a porta do llama", "sessão", "antes", "ontem", "", "yesterdayish", "xwhen we", "last timeless",
])
def test_pergunta_que_nao_e_de_sessao(pergunta):
    assert not eh_pergunta_de_sessao(pergunta)


def test_marcador_colado_a_numero_letra_nao_e_palavra_inteira():
    # Ⅶ e letra para o Rust (Nl): "last time" seguido dele nao termina em fronteira de palavra
    assert not eh_pergunta_de_sessao("last timeⅦ")
    assert eh_pergunta_de_sessao("last time²")  # sobrescrito nao e letra


def test_pacote_so_importa_a_biblioteca_padrao_e_texto_bytes():
    import ast
    from pathlib import Path

    arq = Path(__file__).resolve().parents[1] / "src" / "delegation_core" / "ranqueamento" / "autoridade.py"
    for no in ast.walk(ast.parse(arq.read_text())):
        if isinstance(no, ast.ImportFrom):
            assert not (no.module or "").startswith("delegation_core")
            assert no.level < 2 or no.module == "texto_bytes"
