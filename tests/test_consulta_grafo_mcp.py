"""As quatro ferramentas MCP de consulta a grafo, pela camada do servidor.

O motor tem teste proprio (test_consulta_grafo.py). Aqui se prova a ligacao:
nome de grafo vira caminho, a raiz do codigo vem do registro, e erro sai no
envelope tipado do `erros`, e nao como excecao.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

import delegation_core.server as server
from delegation_core.consulta_grafo import motor


@pytest.fixture
def grafos(tmp_path, monkeypatch):
    raiz = tmp_path / "repo"
    (raiz / "src").mkdir(parents=True)
    (raiz / "src" / "app.py").write_text("def main():\n    carregar()\n\ndef carregar():\n    pass\n")
    gdir = tmp_path / "graphs" / "meu-repo"
    gdir.mkdir(parents=True)
    no = lambda i, l, loc: {"id": i, "label": l, "source_file": "src/app.py",  # noqa: E731
                            "source_location": loc, "file_type": "code", "community": 0}
    (gdir / "graph.json").write_text(json.dumps({
        "nodes": [no("main", "main()", "L1"), no("carregar", "carregar()", "L4")],
        "links": [{"source": "main", "target": "carregar", "relation": "calls", "confidence": "EXTRACTED"}],
    }))
    reg = tmp_path / "graphs" / "registry.json"
    reg.write_text(json.dumps({"meu-repo": {"source_path": str(raiz)}}))
    cfg = SimpleNamespace(graphs_dir=tmp_path / "graphs", graphs_registry_path=reg)
    monkeypatch.setattr(server, "_vault", SimpleNamespace(cfg=cfg))
    motor._CACHE.clear()
    return cfg


def _chamar(ferramenta, **kw):
    return json.loads(asyncio.run(ferramenta(**kw)))


def test_graph_query_devolve_o_texto_do_subgrafo(grafos):
    r = _chamar(server.graph_query, name="meu-repo", question="carregar")
    assert "main() --calls--> carregar()" in r["texto"]


def test_graph_node_traz_quem_chama_e_o_codigo_pela_raiz_do_registro(grafos):
    r = _chamar(server.graph_node, name="meu-repo", term="carregar", code_lines=2)
    assert [d["id"] for d in r["entrada"]] == ["main"]
    assert r["code"]["trecho"] == "def carregar():\n    pass"


def test_graph_node_direcao_invalida_e_erro_tipado(grafos):
    r = _chamar(server.graph_node, name="meu-repo", term="main", direction="lado")
    assert r["error_type"] == "invalid_input"


def test_graph_path(grafos):
    r = _chamar(server.graph_path, name="meu-repo", source="main", target="carregar")
    assert r["achado"] and r["passos"][0]["relacao"] == "calls"


def test_graph_path_no_inexistente_e_nao_encontrado(grafos):
    r = _chamar(server.graph_path, name="meu-repo", source="main", target="zzz")
    assert r["error_type"] == "not_found" and "zzz" in r["error"]


def test_graph_stats(grafos):
    assert _chamar(server.graph_stats, name="meu-repo")["nos"] == 2


def test_grafo_inexistente_e_nao_encontrado_em_todas(grafos):
    for f, kw in [(server.graph_query, {"question": "x"}), (server.graph_node, {"term": "x"}),
                  (server.graph_path, {"source": "a", "target": "b"}), (server.graph_stats, {})]:
        r = _chamar(f, name="nao-existe", **kw)
        assert r["error_type"] == "not_found", f.__name__
