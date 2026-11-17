"""Nota ligada a codigo: citacao distintiva, voto de grafo, indice por grafo, ferramentas."""

from __future__ import annotations

import asyncio
import json
import os
from types import SimpleNamespace

import pytest

import delegation_core.server as server
from delegation_core import codigo_vault
from delegation_core.ligacao_codigo import IndiceDeCodigo, chave_da_citacao, citacoes, ligar


def no(id, label, arq, loc="L1", tipo="code"):
    return {"id": id, "label": label, "source_file": arq, "source_location": loc, "file_type": tipo}


DC = {"nodes": [
    no("dc_fila", "localqueue.py", "src/dc/localqueue.py"),
    no("dc_submit", "submit()", "src/dc/localqueue.py", "L40"),
    no("dc_dev", "detect_device()", "src/dc/embeddings.py", "L147"),
    no("dc_cfg_load", ".load()", "src/dc/config.py", "L90"),
    no("dc_rat", "Porque o drop-in existe", "src/dc/embeddings.py", "L150", "rationale"),
    no("dc_json", "graph.json", "src/dc/graph.json"),
]}
FORK = {"nodes": [no("f_fila", "localqueue.py", "src/dc/localqueue.py"), no("f_dev", "detect_device()", "src/dc/embeddings.py")]}
OUTRO = {"nodes": [no("o_dev", "detect_device()", "x/dev.py"), no("o_run", "run_agent()", "x/agent.py")]
         + [no(f"o_g{i}", "search_graph()", f"x/g{i}.py") for i in range(7)]}


def test_citacoes_so_distintivas():
    t = ("`search` `engine` `localqueue.py` `submit()` `detect_device` `IndiceLexico` `Config.load()` "
         "`ab()` `_` `localqueue.py` `v0.12`")
    assert citacoes(t) == ["localqueue.py", "submit()", "detect_device", "IndiceLexico", "Config.load()"]
    assert [chave_da_citacao(c) for c in ("Config.load()", "src/x/busca.py", "a.b.c_d", "X()")] == \
        ["load", "busca.py", "c_d", "x"]


@pytest.fixture
def idx(tmp_path):
    i = IndiceDeCodigo(tmp_path / "c.sqlite3")
    i.carregar_grafo("delegation-core", DC, "1")
    i.carregar_grafo("delegation-core-TEST", FORK, "1")
    i.carregar_grafo("outro", OUTRO, "1")
    yield i
    i.fechar()


def test_indice_chaves_e_arquivo_sem_duplicata(idx):
    assert [a.id for a in idx.buscar("localqueue.py") if a.grafo == "delegation-core"] == ["dc_fila"]
    assert [a.id for a in idx.buscar("embeddings.py")] == ["file:src/dc/embeddings.py", "file:src/dc/embeddings.py"]
    assert [a.id for a in idx.buscar("load")] == ["dc_cfg_load"]
    assert [a.id for a in idx.buscar("graph.json")] == ["dc_json"]     # nao a chave "json"
    assert idx.buscar("json") == [] and idx.buscar("porque o drop-in existe") == []


def test_voto_escolhe_o_grafo_e_desempata_pelo_nome_citado(idx):
    r = ligar("Na `localqueue.py`, `submit()` chama `detect_device()`.", idx)
    assert r["graph"] == "delegation-core" and r["votes"]["delegation-core"] == 3
    assert [l["cited"] for l in r["links"]] == ["localqueue.py", "submit()", "detect_device()"]
    # empate 2 x 2 x 1: vai para o de nome mais curto
    assert ligar("`localqueue.py` e `detect_device()`", idx)["graph"] == "delegation-core"
    # o nome do grafo citado no texto vence o empate
    assert ligar("no delegation-core-TEST: `localqueue.py`, `detect_device()`", idx)["graph"] == "delegation-core-TEST"
    r = ligar("`detect_device()` e `run_agent()`", idx)
    assert r["graph"] == "outro" and [l["cited"] for l in r["links"]] == ["detect_device()", "run_agent()"]


def test_nome_ambiguo_demais_nao_vota(idx):
    assert ligar("`search_graph()`", idx) == {"graph": None, "votes": {}, "links": []}
    assert ligar("`search_graph()`", idx, max_ambiguo=7)["graph"] == "outro"


def test_sincronizar_so_recarrega_o_que_mudou(tmp_path):
    g1, g2 = tmp_path / "a" / "graph.json", tmp_path / "b" / "graph.json"
    for g, d in ((g1, DC), (g2, OUTRO)):
        g.parent.mkdir()
        g.write_text(json.dumps(d))
    i = IndiceDeCodigo(tmp_path / "c.sqlite3")
    assert i.sincronizar({"a": g1, "b": g2})["reloaded"] == ["a", "b"]
    assert i.sincronizar({"a": g1, "b": g2})["reloaded"] == []
    g1.write_text(json.dumps(FORK))
    st = g1.stat()
    os.utime(g1, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000))
    assert i.sincronizar({"a": g1, "b": g2})["reloaded"] == ["a"]
    assert [a.id for a in i.buscar("localqueue.py") if a.grafo == "a"] == ["f_fila"]
    assert i.sincronizar({"b": g2})["forgotten"] == ["a"] and i.grafos() == ["b"]
    i.fechar()


def _ambiente(tmp_path):
    gd = tmp_path / "graphs"
    for nome, d in (("delegation-core", DC), ("outro", OUTRO)):
        (gd / nome).mkdir(parents=True)
        (gd / nome / "graph.json").write_text(json.dumps(d))
    raiz = tmp_path / "v"
    (raiz / "Fixes").mkdir(parents=True)
    (raiz / "Sessions").mkdir()
    (raiz / "Fixes" / "drop-in.md").write_text("O `detect_device()` nao le variavel; a `localqueue.py` ficou.")
    (raiz / "Fixes" / "outra.md").write_text("`detect_device()` de novo, `detect_device` sem parenteses, e `submit()`.")
    (raiz / "Sessions" / "s.md").write_text("`detect_device()` numa sessao")
    cfg = SimpleNamespace(vault=raiz, graphs_dir=gd, codigo_path=str(tmp_path / "c.sqlite3"), codigo_enabled=True)
    codigo_vault._INDICE.clear()
    codigo_vault._REVERSO.clear()
    return cfg


def test_reverso_e_notas_do_termo(tmp_path):
    cfg = _ambiente(tmp_path)
    r = codigo_vault.notas_do_termo(cfg, "delegation-core", "detect_device")
    [n] = r["nodes_with_notes"]
    assert n["file"] == "src/dc/embeddings.py" and n["notes"] == ["Fixes/drop-in.md", "Fixes/outra.md"]
    assert codigo_vault.notas_do_termo(cfg, "outro", "detect_device")["nodes_with_notes"] == []
    # nota nova muda o reverso
    (cfg.vault / "Fixes" / "nova.md").write_text("`submit()` e `detect_device()`")
    assert "Fixes/nova.md" in codigo_vault.notas_do_termo(cfg, "delegation-core", "submit")["nodes_with_notes"][0]["notes"]


class VaultFalso:
    def __init__(self, cfg):
        self.cfg = cfg

    def find_notes_by_stem(self, nome):
        return [p for p in self.cfg.vault.rglob("*.md") if p.stem == nome]


def test_ferramentas(tmp_path, monkeypatch):
    cfg = _ambiente(tmp_path)
    monkeypatch.setattr(server, "_vault", VaultFalso(cfg))
    r = json.loads(asyncio.run(server.vault_note_code(note="drop-in")))
    assert r["graph"] == "delegation-core"
    assert {t["node_id"] for l in r["links"] for t in l["targets"]} == {"dc_dev", "dc_fila"}
    r = json.loads(asyncio.run(server.graph_notes(name="delegation-core", term="localqueue.py")))
    assert r["nodes_with_notes"][0]["notes"] == ["Fixes/drop-in.md"]
    assert json.loads(asyncio.run(server.graph_notes(name="nada", term="x")))["error_type"] == "not_found"
    assert json.loads(asyncio.run(server.vault_note_code(note="nada")))["error_type"] == "not_found"
    cfg.codigo_enabled = False
    assert json.loads(asyncio.run(server.vault_note_code(note="drop-in")))["error_type"] == "disabled"


def test_sumidos_na_recarga_e_na_primeira_carga(tmp_path):
    i = IndiceDeCodigo(tmp_path / "c.sqlite3")
    i.carregar_grafo("g", DC, "1")
    assert i.sumido("submit") == []
    menos = {"nodes": [n for n in DC["nodes"] if n["id"] != "dc_submit"]}
    i.carregar_grafo("g", menos, "2")
    [s] = i.sumido("submit")
    assert (s["graph"], s["label"], s["file"]) == ("g", "submit()", "src/dc/localqueue.py")
    i.carregar_grafo("g", DC, "3")                      # voltou: sai de sumidos
    assert i.sumido("submit") == []
    # primeira carga de outro grafo, com o grafo anterior do build
    i.carregar_grafo("h", menos, "1", anterior=DC)
    assert [x["graph"] for x in i.sumido("submit")] == ["h"]
    assert i.esquecer_exceto({"g"}) == ["h"] and i.sumido("submit") == []
    i.fechar()


def test_nota_que_cita_codigo_sumido(tmp_path):
    cfg = _ambiente(tmp_path)
    gd = cfg.graphs_dir / "delegation-core"
    (gd / "graph.anterior.json").write_text((gd / "graph.json").read_text())
    (gd / "graph.json").write_text(json.dumps({"nodes": [n for n in DC["nodes"] if n["id"] != "dc_dev"]}))
    codigo_vault._INDICE.clear()
    r = codigo_vault.da_nota(cfg, "Fixes/drop-in.md")
    assert [g["cited"] for g in r["gone"]] == ["detect_device()"]
    assert [n["note"] for n in codigo_vault.notas_com_sumido(cfg)] == ["Fixes/drop-in.md", "Fixes/outra.md"]
    # o nome ainda existe em OUTRO grafo, mas sumiu deste: conta
    assert codigo_vault.da_nota(cfg, "Fixes/outra.md")["gone"][0]["graph"] == "delegation-core"


def test_nota_ligada_ao_fork_aparece_no_original(tmp_path):
    cfg = _ambiente(tmp_path)
    gd = cfg.graphs_dir / "delegation-core-TEST"
    gd.mkdir()
    fork = {"nodes": [no("f_dev", "detect_device()", "src/dc/embeddings.py", "L147"), no("f_sub", "submit()", "src/dc/q.py")]}
    (gd / "graph.json").write_text(json.dumps(fork))
    (cfg.vault / "Fixes" / "fork.md").write_text("No delegation-core-TEST o `detect_device()` e o `submit()`.")
    codigo_vault._INDICE.clear()
    [n] = codigo_vault.notas_do_termo(cfg, "delegation-core", "detect_device")["nodes_with_notes"]
    assert "Fixes/fork.md" in n["notes"] and n["via_graph"] == {"Fixes/fork.md": "delegation-core-TEST"}
    assert "Fixes/drop-in.md" in n["notes"] and "Fixes/drop-in.md" not in n["via_graph"]
    # submit() do fork esta em outro arquivo: nao e a mesma funcao
    [s] = codigo_vault.notas_do_termo(cfg, "delegation-core", "submit")["nodes_with_notes"]
    assert "Fixes/fork.md" not in s["notes"]
