"""Pacote consulta_grafo, sobre um grafo pequeno em que toda resposta e conhecida."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from delegation_core.consulta_grafo import Grafo, carregar
from delegation_core.consulta_grafo import motor

PACOTE = Path(__file__).resolve().parents[1] / "src" / "delegation_core" / "consulta_grafo"


def _no(i, label, arq="src/app.py", tipo="code", loc="L1", com=0):
    return {"id": i, "label": label, "source_file": arq, "source_location": loc,
            "file_type": tipo, "community": com}


def _ln(a, b, rel="calls"):
    return {"source": a, "target": b, "relation": rel, "confidence": "EXTRACTED"}


DADOS = {
    "nodes": [
        _no("app", "app.py"),
        _no("main", "main()", loc="L3"),
        _no("carregar", "carregar_config()", loc="L10"),
        _no("ler", "ler_arquivo()", loc="L20"),
        _no("gravar", "gravar_indice()", loc="L30"),
        _no("carimbo", "stamp_indexed()", arq="src/vault.py", loc="L2"),
        _no("teste", "test_carregar_config_le_o_arquivo()", arq="tests/test_app.py"),
        _no("porque", "Le a config uma vez so, porque o disco e lento", tipo="rationale"),
        _no("solto", "isolado()"),
    ],
    "links": [
        _ln("app", "main", "contains"), _ln("app", "carregar", "contains"),
        _ln("main", "carregar"), _ln("carregar", "ler"), _ln("main", "gravar"),
        _ln("gravar", "carimbo"), _ln("teste", "carregar"),
        _ln("porque", "carregar", "rationale_for"),
        _ln("fantasma", "main"),  # aresta para no inexistente: ignorada
    ],
}


@pytest.fixture
def g():
    return Grafo.de_dados(DADOS)


def test_estatisticas_contam_e_ignoram_aresta_orfa(g):
    e = g.estatisticas()
    assert e["nos"] == 9 and e["arestas"] == 8
    assert e["relacoes"]["calls"] == 5 and "rationale" not in [c["tipo"] for c in e["centrais"]]


def test_centrais_nao_contam_contains(g):
    """app tem duas arestas contains e nada mais; sem o filtro ele empataria com main."""
    assert g.estatisticas(1)["centrais"][0]["id"] == "carregar"


def test_achar_rotulo_identico_vence(g):
    assert g.achar("carregar_config")[0][0] == "carregar"


def test_achar_quebra_snake_e_camel(g):
    assert g.achar("stampIndexed")[0][0] == "carimbo"


def test_achar_pune_teste_a_menos_que_pedido(g):
    assert g.achar("carregar config arquivo")[0][0] == "carregar"
    # a pergunta cobre o nome do teste inteiro: sem a punicao (1,94) ele passa carregar (1,70);
    # com a punicao indevida cairia para 0,58
    assert g.achar("test carregar config le arquivo")[0][0] == "teste"


def test_achar_deixa_racional_de_fora_por_padrao(g):
    assert "porque" not in [n for n, _ in g.achar("disco lento config")]
    assert "porque" in [n for n, _ in g.achar("disco lento", incluir_racional=True)]


def test_resolver_aceita_id_ou_nome(g):
    assert g.resolver("main") == "main" and g.resolver("gravar indice") == "gravar"
    assert g.resolver("zzzz") is None


def test_vizinhos_separa_sentido_e_esconde_contains(g):
    v = g.vizinhos("carregar")
    assert [d["id"] for d in v["saida"]] == ["ler"]
    assert sorted(d["id"] for d in v["entrada"]) == ["main", "porque", "teste"]
    assert "app" in [d["id"] for d in g.vizinhos("carregar", incluir_ruido=True)["entrada"]]


def test_vizinhos_filtra_por_relacao(g):
    v = g.vizinhos("carregar", direcao="entrada", relacoes={"rationale_for"})
    assert [d["id"] for d in v["entrada"]] == ["porque"] and "saida" not in v


def test_caminho_segue_a_direcao(g):
    c = g.caminho("main", "carimbo")
    assert c["achado"] and c["respeita_direcao"] and c["tamanho"] == 2
    assert [p["relacao"] for p in c["passos"]] == ["calls", "calls"]


def test_caminho_contra_a_direcao_cai_para_nao_dirigido(g):
    c = g.caminho("carimbo", "main")
    assert c["achado"] and not c["respeita_direcao"]
    assert [p["sentido"] for p in c["passos"]] == ["<-", "<-"]


def test_caminho_nao_atalha_por_contains(g):
    """main e carregar sao ambos filhos de app; o atalho por contains nao vale."""
    c = g.caminho("ler", "main")
    assert all(p["relacao"] != "contains" for p in c["passos"])


def test_caminho_inexistente(g):
    assert g.caminho("main", "solto") == {"achado": False}


def test_subgrafo_traz_sementes_relacoes_e_porque(g):
    s = g.subgrafo("carregar config", profundidade=1)
    assert s["sementes"][0]["id"] == "carregar"
    assert "carregar_config() --calls--> ler_arquivo()" in s["texto"]
    assert "Le a config uma vez so" in s["texto"]


def test_subgrafo_respeita_orcamento(g):
    s = g.subgrafo("carregar config", orcamento=60)
    assert s["cortado"] and len(s["texto"]) < 120


def test_subgrafo_leque_limita_a_expansao(g):
    assert g.subgrafo("main", profundidade=1, leque=1)["arestas"] == 1


def test_trecho_le_as_linhas_e_nao_sai_da_raiz(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("\n".join(f"linha {i}" for i in range(1, 41)))
    g = Grafo.de_dados(DADOS, tmp_path)
    t = g.trecho("carregar", linhas=3)
    assert t["trecho"] == "linha 10\nlinha 11\nlinha 12"
    fora = Grafo.de_dados({"nodes": [_no("x", "x()", arq="../../etc/passwd")], "links": []}, tmp_path)
    assert fora.trecho("x")["trecho"] is None


def test_carregar_usa_cache_e_invalida_quando_o_arquivo_muda(tmp_path):
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(DADOS))
    a = carregar(p)
    assert carregar(p) is a
    dados2 = json.loads(json.dumps(DADOS))
    dados2["nodes"].append(_no("novo", "novo()"))
    p.write_text(json.dumps(dados2) + " " * 10)
    b = carregar(p)
    assert b is not a and "novo" in b.nos


def test_cache_despeja_o_mais_antigo(tmp_path, monkeypatch):
    monkeypatch.setattr(motor, "MAX_EM_MEMORIA", 1)
    motor._CACHE.clear()
    for nome in ("a", "b"):
        (tmp_path / f"{nome}.json").write_text(json.dumps(DADOS))
        carregar(tmp_path / f"{nome}.json")
    assert len(motor._CACHE) == 1


def test_pacote_nao_importa_o_nucleo():
    proibidos = []
    for arq in PACOTE.glob("*.py"):
        for no in ast.walk(ast.parse(arq.read_text())):
            if isinstance(no, ast.ImportFrom) and (no.level >= 2 or (no.module or "").startswith("delegation_core")):
                proibidos.append(f"{arq.name}: {no.module}")
    assert proibidos == []


# ── casos escolhidos para que cada regra decida sozinha (mutacao os exigiu) ──

def test_rotulo_identico_decide_quando_o_idf_nao_decidiria():
    """gravar e comum (3 nos) e indice raro (2): sem o bonus, `indice()` (1 termo)
    passa `gravar_indice()` (2 termos) na propria busca por "gravar indice"."""
    g = Grafo.de_dados({"nodes": [_no("gi", "gravar_indice()"), _no("i", "indice()"),
                                  _no("g1", "gravar_log()"), _no("g2", "gravar_x()")], "links": []})
    assert g.achar("gravar indice")[0][0] == "gi"


def test_punicao_de_teste_decide():
    """Sem punicao, `test_lote()` (2 termos) passa `processar_lote_grande()` (3)."""
    g = Grafo.de_dados({"nodes": [_no("c", "processar_lote_grande()"),
                                  _no("t", "test_lote()", arq="tests/test_lote.py")], "links": []})
    assert g.achar("lote")[0][0] == "c"


def test_caminho_nao_dirigido_nao_usa_contains_como_atalho():
    """x e y estao no mesmo arquivo f. Pela direcao nao ha caminho de x a y; sem
    direcao, o atalho por contains teria 2 passos e a cadeia de chamadas tem 3."""
    g = Grafo.de_dados({
        "nodes": [_no(n, n) for n in ("f", "x", "y", "a", "b")],
        "links": [_ln("f", "x", "contains"), _ln("f", "y", "contains"),
                  _ln("y", "b"), _ln("b", "a"), _ln("a", "x")],
    })
    c = g.caminho("x", "y")
    assert c["achado"] and not c["respeita_direcao"] and c["tamanho"] == 3


def test_trecho_recusa_caminho_absoluto_que_existe(tmp_path):
    g = Grafo.de_dados({"nodes": [_no("x", "x()", arq="/etc/hostname")], "links": []}, tmp_path)
    t = g.trecho("x")
    assert t["trecho"] is None and t["motivo"] == "arquivo fora da raiz"


def test_cache_nao_guarda_duas_versoes_do_mesmo_arquivo(tmp_path):
    motor._CACHE.clear()
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(DADOS))
    carregar(p)
    p.write_text(json.dumps(DADOS) + " " * 5)
    carregar(p)
    assert len([k for k in motor._CACHE if k[0] == str(p.resolve())]) == 1
