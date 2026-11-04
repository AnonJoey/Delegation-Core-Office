"""search_vault: o resumo escrito pelo modelo local diz que e do modelo local.

Relato do Mac de um colega em 2026-11-04: em modo local a busca levou cerca de
13 s e o resumo inventou uma data. Quem leu o resumo nao tinha como saber que ele
vinha de um modelo menor do que o proprio agente; so o verificador do
delegation-core pegou. O resumo continua sendo entregue, mas agora marcado, e a
marca diz o que fazer com ele.
"""

import asyncio
import json

import pytest

from delegation_core import server
from delegation_core.config import Config


class _Vault:
    def __init__(self, cfg):
        self.cfg = cfg

    def search(self, *a, **k):
        return [{"title": "Nota", "path": "Reference/n.md", "snippet": "texto",
                 "similarity": 0.8, "folder": "Reference", "kind": "note"}]


class _Motor:
    def __init__(self, cfg):
        self.cfg = cfg

    async def invoke(self, *a, **k):
        return "Resumo escrito pelo modelo local com mais de vinte caracteres."

    def budget(self, *a, **k):
        return 100


def _roda(monkeypatch, modo, **kw):
    cfg = Config(vault_path="/v", engine_mode=modo)
    monkeypatch.setattr(server, "_vault", _Vault(cfg))
    monkeypatch.setattr(server, "_engine", _Motor(cfg))
    monkeypatch.setattr(server, "_local_model_queue_stats", lambda: {"running": 0})
    return json.loads(asyncio.run(server.search_vault("q", scope="all", **kw)))


def test_resumo_do_modelo_local_vem_rotulado(monkeypatch):
    r = _roda(monkeypatch, "local")
    assert r["summary"]
    assert r["summary_source"] == "local_model"
    assert "source" in r["summary_warning"].lower()


def test_sem_resumo_nao_ha_rotulo_de_resumo(monkeypatch):
    r = _roda(monkeypatch, "agent")
    assert r["summary"] is None
    assert "summary_source" not in r and "summary_warning" not in r


def test_hybrid_com_use_local_tambem_rotula(monkeypatch):
    r = _roda(monkeypatch, "hybrid", use_local=True)
    assert r["summary"] and r["summary_source"] == "local_model"
