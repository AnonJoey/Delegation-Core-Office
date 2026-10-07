"""Um daemon vivo e travado nao e um daemon que saiu.

O sistema operacional aceita a conexao mesmo com o processo travado; so a
inicializacao da sessao estoura o tempo. Antes, isso virava DaemonUnavailable, a
CLI contava o indice sozinha e o `status` dizia "not initialized: run:
delegation-core reindex", culpando um indice saudavel e recomendando horas de
reindexacao por um problema do daemon.
"""
import socket
import threading
import time

import httpx
import pytest

from delegation_core import daemon
from delegation_core.config import Config


def _cfg(porta):
    return Config(vault_path="/tmp/nao-importa", server_port=porta, server_token="t" * 24)


async def _levanta(exc):
    raise exc


# -- a classificacao, sem rede ------------------------------------------------------

def test_timeout_com_a_porta_ainda_aberta_e_daemon_travado(monkeypatch):
    monkeypatch.setattr(daemon, "is_listening", lambda *a, **k: True)
    with pytest.raises(daemon.DaemonUnresponsive) as e:
        daemon._run(_levanta(httpx.ReadTimeout("sem resposta")), "vault_stats", _cfg(1))
    assert isinstance(e.value, daemon.DaemonCallFailed) and not isinstance(e.value, daemon.DaemonUnavailable)


def test_timeout_com_a_porta_fechada_e_daemon_que_saiu(monkeypatch):
    monkeypatch.setattr(daemon, "is_listening", lambda *a, **k: False)
    with pytest.raises(daemon.DaemonUnavailable):
        daemon._run(_levanta(httpx.ReadTimeout("sem resposta")), "vault_stats", _cfg(1))


def test_conexao_recusada_continua_sendo_daemon_que_saiu(monkeypatch):
    monkeypatch.setattr(daemon, "is_listening", lambda *a, **k: True)
    with pytest.raises(daemon.DaemonUnavailable):
        daemon._run(_levanta(httpx.ConnectError("recusada")), "vault_stats", _cfg(1))


def test_timeout_embrulhado_em_grupo_e_em_runtimeerror_tambem_e_reconhecido(monkeypatch):
    monkeypatch.setattr(daemon, "is_listening", lambda *a, **k: True)

    async def embrulhado():
        try:
            raise ExceptionGroup("grupo", [httpx.ReadTimeout("x")])
        except ExceptionGroup as g:
            raise RuntimeError("Client failed to connect: Failed to initialize server session") from g
    with pytest.raises(daemon.DaemonUnresponsive):
        daemon._run(embrulhado(), "vault_stats", _cfg(1))


def test_sem_cfg_o_comportamento_antigo_nao_muda(monkeypatch):
    with pytest.raises(daemon.DaemonUnavailable):
        daemon._run(_levanta(httpx.ReadTimeout("x")), "vault_stats")


def test_falha_que_nao_e_de_rede_continua_sendo_rejeicao(monkeypatch):
    monkeypatch.setattr(daemon, "is_listening", lambda *a, **k: True)
    with pytest.raises(daemon.DaemonCallFailed) as e:
        daemon._run(_levanta(ValueError("o daemon recusou")), "vault_stats", _cfg(1))
    assert not isinstance(e.value, (daemon.DaemonUnavailable, daemon.DaemonUnresponsive))


# -- ponta a ponta com um daemon falso que aceita e nunca responde -------------------

@pytest.fixture
def daemon_mudo():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(50)
    porta = s.getsockname()[1]
    seguradas = []
    parar = threading.Event()

    def aceitar():
        s.settimeout(0.2)
        while not parar.is_set():
            try:
                c, _ = s.accept()
                seguradas.append(c)
            except OSError:
                pass
    t = threading.Thread(target=aceitar, daemon=True)
    t.start()
    yield porta
    parar.set()
    t.join(2)
    for c in seguradas:
        c.close()
    s.close()


def test_call_tool_contra_um_daemon_mudo_levanta_daemon_unresponsive(daemon_mudo):
    t0 = time.time()
    with pytest.raises(daemon.DaemonUnresponsive):
        daemon.call_tool(_cfg(daemon_mudo), "vault_stats", timeout=1.5)
    assert time.time() - t0 < 20


def test_o_status_nao_conta_o_indice_sozinho_quando_o_daemon_esta_mudo(daemon_mudo, monkeypatch):
    from delegation_core import cli
    from delegation_core import indice_sqlite
    monkeypatch.setattr(daemon, "CALL_TIMEOUT_SEC", 1.5, raising=False)
    abriu = []
    monkeypatch.setattr(indice_sqlite, "ClienteSqlite", lambda *a, **k: abriu.append(1) or (_ for _ in ()).throw(AssertionError("abriu o indice")))
    contagem, origem = cli._index_row_counts(_cfg(daemon_mudo), timeout=1.5)
    assert origem.startswith("daemon-unresponsive") and contagem == {}
    assert abriu == [], "contou o indice por conta propria com o daemon vivo e travado"
