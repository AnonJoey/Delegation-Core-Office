"""`check_network_exposure`: o doctor avisa quando o daemon escuta fora do laco."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from delegation_core import doctor


def _cfg(**mudancas):
    base = {"server_host": "127.0.0.1", "tool_policies": {}, "client_tokens": {}}
    base.update(mudancas)
    return SimpleNamespace(**base)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "[::1]", "127.0.1.1", "LOCALHOST"])
def test_no_laco_esta_tudo_certo(host):
    r = doctor.check_network_exposure(_cfg(server_host=host))
    assert r["check"] == "network_exposure" and r["status"] == "ok"


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.0.10", "meu-servidor", ""])
def test_fora_do_laco_avisa_do_shell_e_do_token_unico(host):
    r = doctor.check_network_exposure(_cfg(server_host=host))
    assert r["status"] == "warn"
    assert "dag_run" in r["detail"] and "allowed for every client" in r["detail"]
    assert "one shared token" in r["detail"]
    assert "127.0.0.1" in r["fix"] and "policy set '*' dag_run block" in r["fix"]


def test_a_politica_e_o_token_por_cliente_aparecem_no_aviso():
    r = doctor.check_network_exposure(_cfg(server_host="0.0.0.0", tool_policies={"*": {"dag_run": "block"}},
                                           client_tokens={"claude-code": "t"}))
    assert r["status"] == "warn", "continua exposto: a politica reduz o dano, nao fecha a porta"
    assert "dag_run is block" in r["detail"] and "one shared token" not in r["detail"]


def test_a_politica_por_classe_alcanca_o_dag_run():
    """Liga as duas mudancas: `dag_run` passou a ser `destructive`, entao a regra por classe vale."""
    r = doctor.check_network_exposure(_cfg(server_host="0.0.0.0", tool_policies={"*": {"destructive": "require_approval"}}))
    assert "dag_run is require_approval" in r["detail"]


def test_e_aviso_e_nunca_erro():
    assert doctor.check_network_exposure(_cfg(server_host="0.0.0.0"))["status"] != "error"


def test_o_check_entra_no_run_all():
    import inspect
    assert "check_network_exposure(cfg)" in inspect.getsource(doctor.run_all)
