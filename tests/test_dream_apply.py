"""dream_apply: o achado confirmado vira aviso dentro da nota velha, no caminho exato, uma vez."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

import delegation_core.server as server
from delegation_core import historico_vault, sonho_vault


@pytest.fixture
def amb(tmp_path, monkeypatch):
    raiz = tmp_path / "v"
    (raiz / "Decisions").mkdir(parents=True)
    velha = raiz / "Decisions" / "gpu.md"
    velha.write_text("BGE na GPU.\n")
    (raiz / "Decisions" / "gpu-antiga-demais.md").write_text("outra nota\n")   # nome contem 'gpu'
    cfg = SimpleNamespace(vault=raiz, sonho_enabled=True, achados_path=str(tmp_path / "a.sqlite3"))
    sonho_vault._ACHADOS.clear()
    indexadas = []
    monkeypatch.setattr(server, "_vault", SimpleNamespace(cfg=cfg, index_note=lambda t, m: indexadas.append(m)))
    monkeypatch.setattr(server, "_post_write_links", lambda *a: None)
    fotos = []
    monkeypatch.setattr(historico_vault, "fotografar", lambda cfg, origem: fotos.append(origem))
    yield SimpleNamespace(cfg=cfg, velha=velha, raiz=raiz, indexadas=indexadas, fotos=fotos)
    sonho_vault._ACHADOS.clear()


def test_aplica_uma_vez_no_caminho_exato(amb):
    sonho_vault.achados(amb.cfg).registrar("Decisions/gpu.md", "Fixes/drop-in.md", "updates",
                                           "BGE na GPU", "drop-in removido", em=1790000000)
    r = json.loads(server.dream_apply(old="Decisions/gpu.md", new="Fixes/drop-in.md"))
    assert r["applied"] is True
    t = amb.velha.read_text()
    assert t.startswith("BGE na GPU.\n") and "[[drop-in]]" in t and '"drop-in removido"' in t
    assert (amb.raiz / "Decisions" / "gpu-antiga-demais.md").read_text() == "outra nota\n"
    assert amb.indexadas[0]["path"] == "Decisions/gpu.md"
    assert amb.fotos == ["antes de dream_apply Decisions/gpu.md", "dream_apply Decisions/gpu.md"]
    r = json.loads(server.dream_apply(old="Decisions/gpu.md", new="Fixes/drop-in.md"))
    assert r["already"] is True and amb.velha.read_text() == t


def test_sem_achado_ou_descartado(amb):
    assert json.loads(server.dream_apply(old="x.md", new="y.md"))["error_type"] == "not_found"
    reg = sonho_vault.achados(amb.cfg)
    reg.registrar("Decisions/gpu.md", "Fixes/drop-in.md", "updates")
    reg.descartar("Decisions/gpu.md", "Fixes/drop-in.md")
    r = json.loads(server.dream_apply(old="Decisions/gpu.md", new="Fixes/drop-in.md"))
    assert r["error_type"] == "not_found" and amb.velha.read_text() == "BGE na GPU.\n"
