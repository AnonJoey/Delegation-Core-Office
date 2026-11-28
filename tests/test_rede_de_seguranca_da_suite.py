"""A rede do conftest que impede a suite de sair da maquina (`_sem_rede_de_verdade`)."""
from __future__ import annotations

import errno
import socket

import pytest


def test_conexao_para_fora_e_recusada_e_anotada(_sem_rede_de_verdade):
    # 192.0.2.0/24 e a faixa de documentacao (RFC 5737): nada responde la.
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(OSError) as e:
            s.connect(("192.0.2.1", 443))
        assert e.value.errno == errno.ENETUNREACH
        assert s.connect_ex(("192.0.2.1", 443)) == errno.ENETUNREACH
    finally:
        s.close()
    with pytest.raises(socket.gaierror):
        socket.getaddrinfo("exemplo.invalid", 443)
    assert sorted(set(_sem_rede_de_verdade)) == ["connect ('192.0.2.1', 443)", "getaddrinfo 'exemplo.invalid'"]
    _sem_rede_de_verdade.clear()        # tentativa de proposito: nao e para falhar este teste


def test_o_laco_continua_funcionando(_sem_rede_de_verdade):
    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.bind(("127.0.0.1", 0))
    servidor.listen(1)
    cliente = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        cliente.connect(servidor.getsockname())
        assert socket.getaddrinfo("localhost", servidor.getsockname()[1])
        assert socket.getaddrinfo("127.0.0.1", 80) and socket.getaddrinfo(None, 80)
    finally:
        cliente.close()
        servidor.close()
    assert _sem_rede_de_verdade == []


def test_ip_literal_nao_e_consulta_de_nome(_sem_rede_de_verdade):
    assert socket.getaddrinfo("192.0.2.1", 443)
    assert _sem_rede_de_verdade == []
