"""saidas.sqlite3: WAL, espera do arquivo destravar e nenhuma falha no lugar da saida do comando."""

import sqlite3

import pytest

from delegation_core import config
from delegation_core.filtros_saida import execucao, motor


@pytest.fixture
def banco(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(execucao, "_CON", {})
    return tmp_path / "saidas.sqlite3"


def test_o_arquivo_de_saidas_abre_em_wal_com_espera(banco):
    c = execucao._con()
    assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert c.execute("PRAGMA busy_timeout").fetchone()[0] == execucao.BUSY_TIMEOUT_MS


def _travar(banco):
    """Outro processo segurando o arquivo para escrita, como o escritor do daemon em laco."""
    outro = sqlite3.connect(str(banco), isolation_level=None)
    outro.execute("BEGIN EXCLUSIVE")
    return outro


def test_guardar_com_o_arquivo_travado_devolve_none_em_vez_de_levantar(banco, monkeypatch):
    monkeypatch.setattr(execucao, "BUSY_TIMEOUT_MS", 50)
    execucao._con()
    outro = _travar(banco)
    try:
        assert execucao.guardar("linha\n" * 50, "ps aux", 0) is None
    finally:
        outro.rollback()
        outro.close()


def test_exibir_mostra_a_saida_inteira_quando_nao_consegue_guardar(banco, monkeypatch):
    """Antes saia `OperationalError: database is locked` no lugar da saida do comando."""
    monkeypatch.setattr(execucao, "BUSY_TIMEOUT_MS", 50)
    execucao._con()
    filtro = next(f for f in motor.carregar() if f.nome == "ps")
    bruto = "USER PID COMMAND\n" + "".join(f"root {i} proc{i}\n" for i in range(600))
    outro = _travar(banco)
    try:
        r = execucao.exibir(filtro, bruto, "ps aux", 0)
    finally:
        outro.rollback()
        outro.close()
    assert r["output"] == bruto
    assert r["recall_hint"] is None


def test_recuperar_nao_espera_o_escritor_em_wal(banco, monkeypatch):
    """Em WAL quem le nao fica atras de quem escreve; no modo antigo o `recall` travava junto."""
    g = execucao.guardar("a\nb\nc\n", "echo", 0)
    monkeypatch.setattr(execucao, "BUSY_TIMEOUT_MS", 50)
    monkeypatch.setattr(execucao, "_CON", {})
    outro = _travar(banco)
    try:
        r = execucao.recuperar(g["hash"])
    finally:
        outro.rollback()
        outro.close()
    assert r is not None and r["total_lines"] == 3


def test_guardar_e_recuperar_seguem_funcionando_sem_trava(banco):
    g = execucao.guardar("um\ndois\ntres\n", "echo", 0)
    r = execucao.recuperar(g["hash"])
    assert r["output"].startswith("um\n") and r["total_lines"] == 3
