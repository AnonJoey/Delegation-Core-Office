"""atencao.json: o daemon compoe, o hook de inicio de sessao mostra cada item uma vez."""

from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from delegation_core import atencao, fatos_vault, sonho_vault
from delegation_core.fatos import Fato

HOOK = Path(__file__).resolve().parents[1] / "src" / "delegation_core" / "hooks" / "session_start_brief.py"


@pytest.fixture(scope="module")
def hook():
    spec = importlib.util.spec_from_file_location("session_start_brief_atencao", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def cfg(tmp_path):
    raiz = tmp_path / "v"
    (raiz / "Fixes").mkdir(parents=True)
    (raiz / "Fixes" / "a.md").write_text(f"abra `{tmp_path}/sumiu.conf`")
    c = SimpleNamespace(vault=raiz, sonho_enabled=True, achados_path=str(tmp_path / "a.sqlite3"),
                        recordacao_enabled=True, recordacao_path=str(tmp_path / "r.sqlite3"),
                        fatos_enabled=True, fatos_path=str(tmp_path / "f.sqlite3"), referencias_enabled=True,
                        codigo_enabled=False)
    sonho_vault._ACHADOS.clear()
    sonho_vault._REGISTRO.clear()
    fatos_vault._ARMAZEM.clear()
    yield c
    sonho_vault._REGISTRO.clear()
    sonho_vault._ACHADOS.clear()
    fatos_vault._ARMAZEM.clear()


def test_compor_junta_as_fontes(cfg, tmp_path, monkeypatch):
    from delegation_core import referencias_vault
    monkeypatch.setattr(referencias_vault, "CASA", str(tmp_path))
    referencias_vault._CACHE.clear()
    sonho_vault.achados(cfg).registrar("Decisions/velha.md", "Fixes/nova.md", "updates", "antes", "agora")
    arm = fatos_vault.armazem(cfg)
    arm.substituir("Fixes/x.md", "2026-09-26", "h", [Fato("llama.cpp", "port", "8181")])
    arm.substituir("Fixes/y.md", "2026-09-01", "h", [Fato("llama.cpp", "port", "8080")])
    d = atencao.compor(cfg, abertos=[{"regra": "saude", "sujeito": "links", "severidade": "aviso",
                                       "mensagem": "12 links quebrados", "desde": 100.5}])
    tipos = [i["tipo"] for i in d["itens"]]
    assert tipos == ["alert", "superseded", "divergent_fact", "dead_paths"] and d["erros"] == {}
    assert d["itens"][0]["chave"] == "alerta:saude|links|100"
    assert "`8181`" in d["itens"][2]["texto"] and "`8080`" in d["itens"][2]["texto"]
    assert d["itens"][3]["chave"] == "mortos:1"


def test_fonte_quebrada_nao_cala_as_outras(cfg, monkeypatch):
    def quebra(c):
        raise RuntimeError("sqlite trancado")
    monkeypatch.setitem(atencao.FONTES, "achados", quebra)
    monkeypatch.setattr(cfg, "referencias_enabled", False)
    d = atencao.compor(cfg, abertos=[{"regra": "r", "sujeito": "s", "desde": 1}])
    assert [i["tipo"] for i in d["itens"]] == ["alert"] and "achados" in d["erros"]


def test_gravar_e_atomico(cfg, tmp_path):
    cfg.referencias_enabled = False
    r = atencao.gravar(cfg, tmp_path, abertos=[])
    assert r == {"itens": 0, "erros": []}
    assert json.loads((tmp_path / "atencao.json").read_text())["itens"] == []
    assert not (tmp_path / "atencao.json.tmp").exists()


def _rodar(hook, tmp_path, monkeypatch, capsys, itens, gerado_em=None, estado=None):
    v = tmp_path / "vault"
    (v / "Reference").mkdir(parents=True, exist_ok=True)
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"vault_path": str(v), "vault_folders": ["Reference"]}))
    st = tmp_path / "brief.json"
    if estado is not None:
        st.write_text(json.dumps(estado))
    elif not st.exists():
        st.write_text(json.dumps({"last_check": time.time() - 60}))
    at = tmp_path / "atencao.json"
    at.write_text(json.dumps({"gerado_em": time.time() if gerado_em is None else gerado_em, "itens": itens}))
    monkeypatch.setattr(hook, "STATE_PATH", st)
    monkeypatch.setattr(hook, "CONFIG_PATH", cfg)
    monkeypatch.setattr(hook, "ATENCAO_PATH", at)
    monkeypatch.setattr(hook, "_trigger_reindex", lambda: False)
    monkeypatch.setattr(hook, "_trigger_maintenance", lambda: False)
    hook.main()
    return capsys.readouterr().out


ITEM = {"chave": "achado:a>b", "tipo": "superseded", "texto": "`a` was updates by `b`", "dica": "dream_findings()"}


def test_hook_mostra_uma_vez_mesmo_sem_nota_nova(hook, tmp_path, monkeypatch, capsys):
    out = _rodar(hook, tmp_path, monkeypatch, capsys, [ITEM])
    assert "## Needs attention" in out and "`a` was updates by `b`" in out
    assert _rodar(hook, tmp_path, monkeypatch, capsys, [ITEM]) == ""
    novo = dict(ITEM, chave="achado:c>d", texto="`c` novo")
    out = _rodar(hook, tmp_path, monkeypatch, capsys, [ITEM, novo])
    assert "`c` novo" in out and "`a` was" not in out


def test_hook_ignora_arquivo_velho_e_mostra_na_primeira_sessao(hook, tmp_path, monkeypatch, capsys):
    assert _rodar(hook, tmp_path, monkeypatch, capsys, [ITEM], gerado_em=time.time() - 2 * 86400) == ""
    out = _rodar(hook, tmp_path, monkeypatch, capsys, [ITEM], estado={})
    assert "Needs attention" in out


def test_hook_limita_itens(hook, tmp_path, monkeypatch, capsys):
    itens = [dict(ITEM, chave=f"k{i}", texto=f"item {i}") for i in range(12)]
    out = _rodar(hook, tmp_path, monkeypatch, capsys, itens)
    assert "item 7" in out and "item 8" not in out and "...and 4 more" in out
    out = _rodar(hook, tmp_path, monkeypatch, capsys, itens)
    assert "item 8" in out and "item 0" not in out


def test_tarefa_de_alertas_grava_atencao(tmp_path, monkeypatch):
    from delegation_core import vigia
    chamadas = []
    monkeypatch.setattr(atencao, "gravar", lambda cfg, d, abertos: chamadas.append(abertos) or {"itens": 0})
    v = SimpleNamespace(alertas=SimpleNamespace(avaliar=lambda ctx: {"eventos": [], "abertos": [], "pendentes": []},
                                                abertos=lambda: [{"regra": "x"}]),
                        cfg=SimpleNamespace(), config_dir=tmp_path, contexto=lambda: None,
                        vault=None, tracker=None, submeter=None)
    monkeypatch.setattr(vigia, "avisar", lambda *a: None)
    r = vigia.Vigia.acoes(v)["alertas"]({})
    assert r["atencao"] == {"itens": 0} and chamadas == [[{"regra": "x"}]]


def test_codigo_sumido_vira_item(cfg, tmp_path):
    from delegation_core import codigo_vault
    gd = tmp_path / "graphs" / "painel"
    gd.mkdir(parents=True)
    no = lambda i, l: {"id": i, "label": l, "source_file": "src/main.js", "file_type": "code"}  # noqa: E731
    (gd / "graph.anterior.json").write_text(json.dumps({"nodes": [no("a", "renderFolderList()"), no("b", "init()")]}))
    (gd / "graph.json").write_text(json.dumps({"nodes": [no("b", "init()")]}))
    (cfg.vault / "Fixes" / "painel.md").write_text("O `renderFolderList()` monta a arvore.")
    cfg.codigo_enabled, cfg.graphs_dir, cfg.codigo_path = True, tmp_path / "graphs", str(tmp_path / "c.sqlite3")
    cfg.referencias_enabled = False
    codigo_vault._INDICE.clear()
    d = atencao.compor(cfg)
    [i] = [i for i in d["itens"] if i["tipo"] == "code_gone"]
    assert "`renderFolderList()`" in i["texto"] and i["chave"] == "sumido:Fixes/painel.md|renderFolderList()"
    codigo_vault._INDICE.clear()


def test_lacuna_vira_item(cfg):
    cfg.referencias_enabled = False
    reg = sonho_vault.registro(cfg)
    for _ in range(2):
        reg.registrar("Qual a porta do Paperclip?", [], confianca="low", melhor=0.3)
    reg.registrar("so uma vez", [], confianca="low", melhor=0.2)
    reg.registrar("respondida", [], confianca="low", melhor=0.2)
    reg.registrar("respondida", ["a.md"], confianca="high", melhor=0.9)
    [i] = [i for i in atencao.compor(cfg)["itens"] if i["tipo"] == "knowledge_gap"]
    assert "asked 2x" in i["texto"] and "Paperclip" in i["texto"] and i["chave"] == "lacuna:qual a porta do paperclip?"


def _grava(tmp_path, itens, gerado_em=None):
    (tmp_path / "atencao.json").write_text(json.dumps({"gerado_em": time.time() if gerado_em is None else gerado_em,
                                                       "itens": itens}))


def test_para_cliente_separa_o_visto_por_cliente(tmp_path):
    itens = [dict(ITEM, chave=f"k{i}", texto=f"item {i}") for i in range(10)]
    _grava(tmp_path, itens)
    a = atencao.para_cliente(tmp_path, "claude-desktop")
    assert [x["what"] for x in a["new"]] == [f"item {i}" for i in range(8)] and a["not_shown_yet"] == 2
    assert a["new"][0] == {"kind": "superseded", "what": "item 0", "look_with": "dream_findings()"}
    b = atencao.para_cliente(tmp_path, "claude-desktop")
    assert [x["what"] for x in b["new"]] == ["item 8", "item 9"] and b["total"] == 10
    assert atencao.para_cliente(tmp_path, "claude-desktop")["new"] == []
    assert len(atencao.para_cliente(tmp_path, "codex")["new"]) == 8          # outro cliente, outro visto


def test_para_cliente_sem_arquivo_ou_velho(tmp_path):
    assert atencao.para_cliente(tmp_path, "x") is None
    _grava(tmp_path, [ITEM], gerado_em=time.time() - 2 * 86400)
    assert atencao.para_cliente(tmp_path, "x") is None
    (tmp_path / "atencao.json").write_text("{quebrado")
    assert atencao.para_cliente(tmp_path, "x") is None


def test_heartbeat_traz_attention(tmp_path, monkeypatch):
    import delegation_core.server as server
    from delegation_core import config
    _grava(tmp_path, [ITEM])
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(server, "_current_client_name", lambda default="unknown": "codex")
    r = server._atencao_do_cliente()
    assert r["new"][0]["what"] == ITEM["texto"]
    monkeypatch.setattr(atencao, "para_cliente", lambda *a: 1 / 0)
    assert server._atencao_do_cliente() is None


def test_ordem_de_importancia():
    """O que diz 'isto esta errado' vem antes do que diz 'confira': so 8 chegam por sessao."""
    assert list(atencao.FONTES) == ["alertas", "achados", "codigo_sumido", "divergencias", "codigo_mudado",
                                    "lacunas", "mortos"]
