"""O heartbeat responde "starting" na partida em vez de esperar o indice abrir.

Diagnostico de 26/10/2026: depois de reiniciar o Mac o indice levava cerca de 25 s para abrir
depois de a porta abrir, e o Claude Code desiste de reconectar em cerca de 15 s. O get_stats()
do heartbeat espera o indice, entao o cliente via o daemon travado e a primeira sessao abria
sem as ferramentas.
"""
import asyncio
import json

from delegation_core import server
from delegation_core.config import Config


class _Engine:
    def __init__(self, tmp_path):
        self.cfg = Config(vault_path=str(tmp_path), engine_mode="agent")


class _Vault:
    def __init__(self, ja_ficou_pronto, init_error=None):
        self.ja_ficou_pronto = ja_ficou_pronto
        self.init_error = init_error
        self.esperou_o_indice = False

    def get_stats(self):
        self.esperou_o_indice = True      # o que o daemon real faz esperando a thread de carga
        return {}

    def get_health_summary(self, force=False):
        return {}


class _Tracker:
    def summary(self):
        return {}


def _bate(monkeypatch, tmp_path, vault):
    monkeypatch.setattr(server, "_engine", _Engine(tmp_path))
    monkeypatch.setattr(server, "_vault", vault)
    monkeypatch.setattr(server, "_tracker", _Tracker())
    return json.loads(asyncio.run(server.heartbeat()))


def test_na_partida_responde_starting_sem_esperar_o_indice(tmp_path, monkeypatch):
    vault = _Vault(ja_ficou_pronto=False)
    r = _bate(monkeypatch, tmp_path, vault)
    assert r["status"] == "starting" and "heartbeat again" in r["detail"]
    assert vault.esperou_o_indice is False


def test_depois_de_pronto_o_heartbeat_completo_volta(tmp_path, monkeypatch):
    r = _bate(monkeypatch, tmp_path, _Vault(ja_ficou_pronto=True))
    assert r["status"] == "healthy"


def test_init_com_erro_nao_e_starting(tmp_path, monkeypatch):
    """Falha de BGE ou do indice e `degraded`, nao uma partida que nunca termina."""
    r = _bate(monkeypatch, tmp_path, _Vault(ja_ficou_pronto=False, init_error="dll bloqueada"))
    assert r["status"] == "degraded"
