"""Boletim diario: junta o que os sistemas gravaram e so escreve se houver o que dizer."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest

from delegation_core import boletim, historico_vault, sonho_vault


class VaultFalso:
    def __init__(self, cfg):
        self.cfg = cfg

    def index_note(self, t, m):
        return True

    def stamp_indexed(self, r):
        pass


@pytest.fixture
def base(tmp_path, monkeypatch):
    from delegation_core import notewriter
    from delegation_core.config import Config
    monkeypatch.setattr(notewriter, "post_write_links", lambda *a, **k: None)
    raiz = tmp_path / "vault"
    for p in ("Fixes", "Sessions", "Reference"):
        (raiz / p).mkdir(parents=True)
    conf = tmp_path / "conf"
    conf.mkdir()
    cfg = Config(vault_path=str(raiz), vault_folders=["Fixes", "Sessions", "Reference"],
                 recordacao_path=str(tmp_path / "rec.sqlite3"))
    historico_vault._INSTANCIAS.clear()
    sonho_vault._REGISTRO.clear()
    yield SimpleNamespace(cfg=cfg, raiz=raiz, conf=conf, v=VaultFalso(cfg))
    for h in historico_vault._INSTANCIAS.values():
        h.fechar()
    historico_vault._INSTANCIAS.clear()
    for r in sonho_vault._REGISTRO.values():
        r.fechar()
    sonho_vault._REGISTRO.clear()


def test_nada_a_dizer_nao_escreve(base):
    r = boletim.gerar(base.v, base.conf, horas=24)
    assert "nota" not in r and r["notas_mudadas"] == 0


def test_boletim_junta_mudanca_alerta_tarefa_sonho_e_lacuna(base):
    (base.raiz / "Fixes" / "a.md").write_text("x")
    historico_vault.fotografar(base.cfg)  # linha de base
    (base.raiz / "Fixes" / "a.md").write_text("x com Related")
    historico_vault.fotografar(base.cfg, origem="relink_folder Fixes")
    (base.conf / "alertas.json").write_text(json.dumps({"alertas": {"k": {
        "estado": "disparando", "severidade": "critico", "mensagem": "3 GB livres"}}, "eventos": []}))
    (base.conf / "agenda.json").write_text(json.dumps({"reindex-noturno": {
        "falhas_seguidas": 1, "ultimo_erro": "OSError: disco", "ultima_execucao": "2026-01-01T00:00:00"}}))
    (base.raiz / "Reference" / "2026-09-27-Sonho de 2026-09-27 - 1.md").write_text("x")
    reg = sonho_vault.registro(base.cfg)
    reg.registrar("onedrive da soteria", [], confianca="low")
    reg.registrar("onedrive da soteria", [], confianca="low")
    tracker = SimpleNamespace(list_processes=lambda status: [
        {"name": "velho", "updated": "2026-01-01T00:00:00"}])
    r = boletim.gerar(base.v, base.conf, tracker=tracker, horas=24)
    texto = (base.raiz / r["nota"]).read_text()
    assert r["nota"].startswith("Sessions/") and "gerado_por: boletim" in texto
    for trecho in ("[critico] 3 GB livres", "reindex-noturno: OSError: disco", "[[2026-09-27-Sonho de 2026-09-27 - 1]]",
                   "relink_folder Fixes: 1", "onedrive da soteria (2 vezes)", "velho ("):
        assert trecho in texto, trecho
    assert "—" not in texto


def test_origem_de_varredura_vira_manual_ou_externo(base):
    (base.raiz / "Fixes" / "b.md").write_text("y")
    historico_vault.fotografar(base.cfg)
    (base.raiz / "Fixes" / "b.md").write_text("y editado num editor")
    historico_vault.fotografar(base.cfg)
    titulo, texto = boletim.redigir(boletim.coletar(base.cfg, base.conf, time.time() - 3600), "2026-09-27")
    assert "manual ou externo: 1" in texto and "1 notas mudaram" in titulo


def test_boletim_anterior_nao_e_noticia(base):
    (base.raiz / "Sessions" / "2026-09-26-Boletim de 2026-09-26 - x.md").write_text("velho")
    historico_vault.fotografar(base.cfg)
    assert boletim.coletar(base.cfg, base.conf, time.time() - 3600)["mudancas"] == []


def test_sonho_nao_sonha_nota_gerada_por_sistema(base):
    p = base.raiz / "Sessions" / "2026-09-27-Boletim de hoje.md"
    p.write_text("---\ngerado_por: boletim\n---\nx")
    assert "Sessions/2026-09-27-Boletim de hoje.md" not in sonho_vault.notas_recentes(base.cfg, 2, 50)


def test_primeira_foto_de_nota_antiga_e_linha_de_base_nao_mudanca(base):
    """O caso real: no dia da primeira varredura, o boletim dizia '500 notas mudaram'."""
    (base.raiz / "Fixes" / "2025-01-01-antiga.md").write_text("velha")
    (base.raiz / "Fixes" / "sem data.md").write_text("velha tambem")
    historico_vault.fotografar(base.cfg)
    f = boletim.coletar(base.cfg, base.conf, time.time() - 3600)
    assert f["mudancas"] == [] and f["linha_de_base"] == 2
    assert not boletim.tem_o_que_dizer(f)
    (base.raiz / "Fixes" / "2025-01-01-antiga.md").write_text("mudou de verdade")
    historico_vault.fotografar(base.cfg, origem="relink_folder Fixes")
    f = boletim.coletar(base.cfg, base.conf, time.time() - 3600)
    assert [m["caminho"] for m in f["mudancas"]] == ["Fixes/2025-01-01-antiga.md"]


def test_nota_nova_de_verdade_conta_como_mudanca(base):
    hoje = time.strftime("%Y-%m-%d")
    (base.raiz / "Fixes" / f"{hoje}-nova.md").write_text("escrita hoje")
    historico_vault.fotografar(base.cfg)
    f = boletim.coletar(base.cfg, base.conf, time.time() - 3600)
    assert [m["caminho"] for m in f["mudancas"]] == [f"Fixes/{hoje}-nova.md"] and f["linha_de_base"] == 0
