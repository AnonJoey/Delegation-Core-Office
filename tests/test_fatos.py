"""Fatos duraveis: extracao validada pelo texto, armazem por nota, agenda e ferramenta."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

import delegation_core.server as server
from delegation_core import fatos_vault
from delegation_core.config import Config
from delegation_core.engine import DelegationEngine
from delegation_core.fatos import ArmazemDeFatos, Fato, extrair
from delegation_core.fatos.extracao import _objetos, chave

NOTA = "O daemon escuta na porta **8787** e usa o modelo `gemma-4-12B`. Config em `~/.delegation_core/config.json`."


def modelo(*fatos, cru=None):
    def perguntar(system, prompt):
        assert "durable facts" in system and "Note:" in prompt
        return cru if cru is not None else json.dumps({"facts": list(fatos)})
    return perguntar


def f(s, a, v, q=""):
    return {"subject": s, "attribute": a, "value": v, "quote": q}


def test_valor_tem_que_estar_no_texto():
    r = extrair(NOTA, modelo(f("delegation-core daemon", "port", "8787"),
                             f("delegation-core daemon", "model", "Gemma-4-12B"),
                             f("delegation-core daemon", "port", "8797"),   # inventado
                             f("daemon", "setting:mode", "asynchronous"),   # reescrito
                             f("", "port", "8787"), f("x", "", "8787")))
    assert [(x.atributo, x.valor) for x in r] == [("port", "8787"), ("model", "Gemma-4-12B")]


def test_vocabulario_fechado_e_valor_curto():
    texto = NOTA + " O daemon tem RLock mais tmp+fsync+replace para cada escrita do registro de jobs sempre."
    r = extrair(texto, modelo(f("daemon", "test_count", "8787"), f("daemon", "setting:", "8787"),
                              f("daemon", "Setting:listen_port", "8787"), f("daemon", "PORT", "8787"),
                              f("daemon", "setting:locking",
                                "tem RLock mais tmp+fsync+replace para cada escrita do registro de jobs sempre")))
    assert [x.atributo for x in r] == ["setting:listen_port", "port"]
    eco = extrair("ver `hooks/session_export.py`", modelo(f("hooks/session_export.py", "path", "hooks/session_export.py")))
    assert eco == []
    link = extrair("ver [[2026-09-03-GS]]", modelo(f("GS", "repository", "[[2026-09-03-GS]]")))
    assert link == []


def test_repetido_sai_e_nota_vazia_nem_pergunta():
    r = extrair(NOTA, modelo(f("Daemon", "Port", "8787"), f("daemon:", "port", "8787")))
    assert len(r) == 1
    assert extrair("   ", lambda s, p: pytest.fail("nao devia perguntar")) == []


def test_resposta_cortada_aproveita_objetos_inteiros():
    cru = '{"facts": [{"subject": "daemon", "attribute": "port", "value": "8787", "quote": "q"}, {"subject": "dae'
    assert [x.valor for x in extrair(NOTA, modelo(cru=cru))] == ["8787"]
    assert _objetos("nada aqui") == []


def test_chave_agrupa_grafias():
    assert chave("GDrive:") == chave("gdrive") == "gdrive"
    assert chave("config path") == chave("Config_Path") == "config_path"


@pytest.fixture
def arm(tmp_path):
    a = ArmazemDeFatos(tmp_path / "f.sqlite3")
    yield a
    a.fechar()


def test_armazem_valor_atual_e_divergencia(arm):
    arm.substituir("Fixes/velha.md", "2026-09-02", "h1", [Fato("daemon", "port", "8787"), Fato("BGE", "device", "GPU")])
    arm.substituir("Fixes/nova.md", "2026-09-26", "h2", [Fato("Daemon", "Port", "8797"), Fato("BGE", "device", "gpu")])
    [g] = arm.buscar("port")
    assert g["current"] == "8797" and g["current_from"] == "Fixes/nova.md" and g["divergent"]
    assert [v["date"] for v in g["values"]] == ["2026-09-26", "2026-09-02"]
    [d] = arm.divergencias()
    assert d["attribute"].lower() == "port"   # GPU e gpu sao o mesmo valor
    assert arm.buscar(sujeito="bge")[0]["divergent"] is False
    assert arm.buscar("porta inexistente") == []
    assert arm.estatisticas() == {"notes": 2, "facts": 4, "subjects_attributes": 2}


def test_armazem_substitui_por_nota_e_esquece_apagada(arm):
    arm.substituir("a.md", "2026-09-01", "h1", [Fato("x", "y", "1"), Fato("x", "z", "2")])
    assert not arm.precisa("a.md", "h1") and arm.precisa("a.md", "h2") and arm.precisa("b.md", "h1")
    arm.substituir("a.md", "2026-09-01", "h2", [Fato("x", "y", "3")])
    assert [g["current"] for g in arm.buscar()] == ["3"]
    arm.substituir("b.md", "2026-09-01", "h", [Fato("w", "k", "4")])
    assert arm.esquecer_exceto({"b.md"}) == 1
    assert arm.estatisticas()["notes"] == 1 and arm.buscar("x") == []


def _vault(tmp_path):
    raiz = tmp_path / "v"
    for p in ("Fixes", "Decisions", "Sessions"):
        (raiz / p).mkdir(parents=True)
    (raiz / "Fixes" / "2026-09-26-porta.md").write_text("O daemon agora escuta na porta 8797.")
    (raiz / "Decisions" / "2026-09-02-porta.md").write_text("Decidido: daemon na porta 8787.")
    (raiz / "Decisions" / "2026-09-03-gerada.md").write_text("---\ngerado_por: sonho\n---\nporta 1")
    (raiz / "Sessions" / "2026-09-27-s.md").write_text("porta 9999")
    cfg = Config(vault_path=str(raiz), vault_folders=["Fixes", "Decisions", "Sessions"],
                 fatos_path=str(tmp_path / "f.sqlite3"), server_token="tok-secreto-1234567890")
    fatos_vault._ARMAZEM.clear()
    return SimpleNamespace(cfg=cfg)


def perguntar_porta(system, prompt):
    import re
    m = re.search(r"porta (\d+)", prompt)
    return json.dumps({"facts": [f("daemon", "port", m.group(1))]})


def test_extrair_pendentes_so_notas_vivas_e_so_uma_vez(tmp_path):
    v = _vault(tmp_path)
    r = fatos_vault.extrair_pendentes(v, perguntar=perguntar_porta)
    assert (r["extracted_notes"], r["facts"], r["pending_left"]) == (2, 2, 0)
    [g] = fatos_vault.armazem(v.cfg).buscar("port")
    assert g["current"] == "8797" and len(g["values"]) == 2
    r = fatos_vault.extrair_pendentes(v, perguntar=lambda s, p: pytest.fail("nota sem mudanca"))
    assert r["extracted_notes"] == 0
    (v.cfg.vault / "Fixes" / "2026-09-26-porta.md").unlink()
    r = fatos_vault.extrair_pendentes(v, perguntar=perguntar_porta)
    assert r["forgotten_notes"] == 1
    assert fatos_vault.armazem(v.cfg).buscar("port")[0]["current"] == "8787"
    fatos_vault._ARMAZEM.clear()


def test_prompt_novo_reextrai(tmp_path, monkeypatch):
    from delegation_core.fatos import extracao
    v = _vault(tmp_path)
    fatos_vault.extrair_pendentes(v, perguntar=perguntar_porta)
    assert fatos_vault.pendentes(v.cfg) == []
    monkeypatch.setattr(extracao, "SISTEMA", extracao.SISTEMA + " v3")
    assert len(fatos_vault.pendentes(v.cfg)) == 2
    fatos_vault._ARMAZEM.clear()


def test_maximo_e_falha_de_uma_nota(tmp_path):
    v = _vault(tmp_path)
    r = fatos_vault.extrair_pendentes(v, maximo=1, perguntar=perguntar_porta)
    assert r["extracted_notes"] == 1 and r["pending_left"] == 1

    def quebra(system, prompt):
        raise TimeoutError("modelo parado")
    r = fatos_vault.extrair_pendentes(v, perguntar=quebra)
    assert r["extracted_notes"] == 0 and len(r["failed"]) == 1
    fatos_vault._ARMAZEM.clear()


def test_segredo_nao_vira_fato(tmp_path):
    v = _vault(tmp_path)
    (v.cfg.vault / "Fixes" / "2026-09-20-chave.md").write_text("token do daemon: tok-secreto-1234567890")
    fatos_vault.extrair_pendentes(v, perguntar=lambda s, p: json.dumps({"facts": [
        f("daemon", "setting:token", "tok-secreto-1234567890")]}) if "tok-" in p else perguntar_porta(s, p))
    arm = fatos_vault.armazem(v.cfg)
    assert arm.buscar("token") == [] and arm.estatisticas()["notes"] == 3  # a nota foi lida
    fatos_vault._ARMAZEM.clear()


def test_ferramenta_e_desligado(tmp_path, monkeypatch):
    v = _vault(tmp_path)
    fatos_vault.extrair_pendentes(v, perguntar=perguntar_porta)
    monkeypatch.setattr(server, "_vault", v)
    r = json.loads(asyncio.run(server.vault_facts(query="port")))
    assert r["groups"][0]["current"] == "8797" and r["stats"]["notes"] == 2
    assert json.loads(asyncio.run(server.vault_facts(divergent=True)))["groups"][0]["divergent"]
    v.cfg.fatos_enabled = False
    assert json.loads(asyncio.run(server.vault_facts()))["error_type"] == "disabled"
    fatos_vault._ARMAZEM.clear()


def test_agenda_tem_a_tarefa_de_fatos():
    from delegation_core.vigia import TAREFAS_PADRAO
    assert any(t["acao"] == "fatos" for t in TAREFAS_PADRAO)


@pytest.mark.parametrize("tarefa,pedido", [("digestao", 1200), ("fatos", 1800), ("sonho", 400)])
def test_tarefa_de_fundo_recebe_o_que_pede(tarefa, pedido):
    """O reduce da digestao pedia 1200 e recebia 512, calado, pelo teto do 'default'."""
    assert DelegationEngine(Config(budget_mode="normal")).budget(tarefa, pedido) == pedido


def test_por_termos_exige_sujeito_e_atributo(arm):
    arm.substituir("a.md", "2026-09-25", "h", [Fato("llama.cpp", "port", "8181"), Fato("llama.cpp", "model", "gemma"),
                                               Fato("delegation-core", "setting:llama_ctx", "16384")])
    arm.substituir("b.md", "2026-09-01", "h", [Fato("llama.cpp", "port", "8080")])
    [g] = arm.por_termos(["qual", "porta", "llama"])
    assert (g["attribute"], g["current"], g["divergent"]) == ("port", "8181", True)
    assert arm.por_termos(["llama"]) == []            # so sujeito: nada
    assert arm.por_termos(["porta"]) == []            # so atributo: nada
    assert [g["attribute"] for g in arm.por_termos(["modelo", "llama.cpp"])] == ["model"]
    assert [g["subject"] for g in arm.por_termos(["delegation", "llama_ctx"])] == ["delegation-core"]
    assert arm.por_termos([]) == [] and arm.por_termos(["a", "de"]) == []
    arm.substituir("c.md", "2026-09-02", "h", [Fato("gemma model", "model", "12B"), Fato("go", "version", "1.22")])
    assert arm.por_termos(["model"]) == []            # uma palavra nao vale por sujeito e atributo
    assert [g["current"] for g in arm.por_termos(["versao", "go"])] == ["1.22"]


def test_search_vault_traz_fatos(tmp_path, monkeypatch):
    v = _vault(tmp_path)
    fatos_vault.extrair_pendentes(v, perguntar=perguntar_porta)
    cfg = v.cfg
    cfg.busca_hibrida, cfg.recordacao_enabled, cfg.sonho_enabled = False, False, False

    class V:
        def __init__(self):
            self.cfg = cfg

        def search(self, query, **k):
            return [{"path": "Fixes/2026-09-26-porta.md", "title": "p", "similarity": 0.7, "snippet": ""}]

    monkeypatch.setattr(server, "_vault", V())
    monkeypatch.setattr(server, "_engine", SimpleNamespace(cfg=cfg))
    r = json.loads(asyncio.run(server.search_vault(query="qual a porta do daemon", scope="notes")))
    [fa] = r["facts"]
    assert fa["current"] == "8797" and fa["divergent"] and fa["other_values"][0]["value"] == "8787"
    r = json.loads(asyncio.run(server.search_vault(query="bolo de cenoura", scope="notes")))
    assert "facts" not in r
    fatos_vault._ARMAZEM.clear()


def test_divergencia_so_em_atributo_unico_e_valor_que_nao_contem_o_outro(arm):
    arm.substituir("a.md", "2026-09-02", "h", [Fato("proj", "path", "~/a"), Fato("ollama", "port", ":11434"),
                                               Fato("ollama", "host", "localhost"), Fato("jogo", "version", "0.4-pc"),
                                               Fato("x", "setting:modo", "agent")])
    arm.substituir("b.md", "2026-09-20", "h", [Fato("proj", "path", "~/b"), Fato("ollama", "port", "11434"),
                                               Fato("ollama", "host", "localhost:11434"), Fato("jogo", "version", "0.4.1"),
                                               Fato("x", "setting:modo", "hybrid")])
    arm.substituir("c.md", "2026-09-21", "h", [Fato("y", "version", "1.0"), Fato("y", "version", "2.0")])
    assert sorted(g["subject"] for g in arm.divergencias()) == ["jogo", "x"]
    assert arm.buscar(sujeito="proj")[0]["divergent"] is False       # path e multiplo
    assert arm.buscar(sujeito="y")[0]["divergent"] is False          # mesma nota nao diverge de si
    # o par mostrado e de notas diferentes, mesmo quando a mais nova tem dois valores
    arm.substituir("d.md", "2026-09-22", "h", [Fato("z", "version", "NVIDIA 595"), Fato("z", "version", "kernel 7")])
    arm.substituir("e.md", "2026-06-18", "h", [Fato("z", "version", "build 236")])
    [g] = arm.buscar(sujeito="z")
    assert {c["note"] for c in g["conflict"]} == {"d.md", "e.md"}


def test_como_estava_em_uma_data(arm):
    arm.substituir("a.md", "2026-08-01", "h", [Fato("daemon", "port", "8080")])
    arm.substituir("b.md", "2026-09-20", "h", [Fato("daemon", "port", "8787")])
    assert arm.buscar("port")[0]["current"] == "8787"
    [g] = arm.buscar("port", ate="2026-08-15")
    assert g["current"] == "8080" and len(g["values"]) == 1 and g["divergent"] is False
    assert arm.buscar(ate="2026-07-01") == []
    assert arm.buscar(sujeito="daemon", ate="2026-09-20")[0]["current"] == "8787"


def test_ferramenta_as_of(tmp_path, monkeypatch):
    v = _vault(tmp_path)
    fatos_vault.extrair_pendentes(v, perguntar=perguntar_porta)
    monkeypatch.setattr(server, "_vault", v)
    r = json.loads(asyncio.run(server.vault_facts(query="port", as_of="2026-09-10")))
    assert r["groups"][0]["current"] == "8787"
    assert json.loads(asyncio.run(server.vault_facts(as_of="ontem")))["error_type"] == "failure"
    fatos_vault._ARMAZEM.clear()


def test_casa_escrita_de_jeitos_diferentes_nao_diverge(arm):
    import os
    arm.substituir("a.md", "2026-09-01", "h", [Fato("dc", "config_path", "$HOME/.delegation_core/config.json")])
    arm.substituir("b.md", "2026-09-20", "h", [Fato("dc", "config_path", "~/.delegation_core/")])
    arm.substituir("c.md", "2026-09-21", "h", [Fato("dc", "config_path", os.path.expanduser("~") + "/.delegation_core")])
    assert arm.divergencias() == []


def test_escrita_de_nota_viva_agenda_extracao(tmp_path):
    v = _vault(tmp_path)
    jobs = []
    sub = lambda nome, fn, *a: jobs.append((nome, a)) or "job1"  # noqa: E731
    assert fatos_vault.apos_escrita(v, "Fixes/2026-09-26-porta.md", submeter=sub) == "job1"
    assert fatos_vault.apos_escrita(v, "Sessions/2026-09-27-s.md", submeter=sub) is None
    v.cfg.fatos_na_escrita = False
    assert fatos_vault.apos_escrita(v, "Fixes/2026-09-26-porta.md", submeter=sub) is None
    assert [j[0] for j in jobs] == ["fatos_nota"]
    r = fatos_vault.extrair_uma(v, "Fixes/2026-09-26-porta.md", perguntar=perguntar_porta)
    assert r == {"note": "Fixes/2026-09-26-porta.md", "facts": 1}
    assert fatos_vault.extrair_uma(v, "Fixes/2026-09-26-porta.md", perguntar=perguntar_porta)["skipped"]
    assert fatos_vault.extrair_uma(v, "Decisions/2026-09-03-gerada.md")["skipped"]
    fatos_vault._ARMAZEM.clear()


def test_post_write_links_chama_a_extracao(tmp_path, monkeypatch):
    from delegation_core import notewriter
    chamadas = []
    monkeypatch.setattr(fatos_vault, "apos_escrita", lambda vault, rel: chamadas.append(rel))
    vault = SimpleNamespace(cfg=SimpleNamespace(), link_note=lambda *a, **k: None)
    notewriter.post_write_links(vault, tmp_path / "x.md", "Fixes/x.md", "Fixes", "x")
    assert chamadas == ["Fixes/x.md"]
