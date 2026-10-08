"""`delegation-core service stop|start|restart` existem de verdade.

O README, o guia do indice SQLite e quatro mensagens do proprio CLI mandam rodar
`delegation-core service stop` antes de migrar o indice e `service start`
depois. O argparse so aceitava install, uninstall e status: quem seguia a
instrucao recebia "invalid choice" no primeiro passo. `service.stop/start/restart`
ja existiam (usados pelo `update`), faltava ligar a CLI.

Tudo com fakes: nenhum teste toca o gerenciador de servico real.
"""
import sys

import pytest

from delegation_core import cli, service


def _rodar(monkeypatch, acao: str) -> int:
    monkeypatch.setattr(sys, "argv", ["delegation-core", "service", acao])
    try:
        return cli.main() or 0
    except SystemExit as e:
        return int(e.code or 0)


@pytest.mark.parametrize("acao", ["stop", "start", "restart"])
def test_a_acao_chama_a_funcao_certa_e_sai_com_zero(monkeypatch, acao):
    chamadas = []
    for nome in ("stop", "start", "restart"):
        monkeypatch.setattr(service, nome, lambda n=nome, **_k: chamadas.append(n) or {"action": n, "status": "ok"})
    assert _rodar(monkeypatch, acao) == 0
    assert chamadas == [acao]


@pytest.mark.parametrize("acao", ["stop", "start", "restart"])
def test_falha_do_gerenciador_nao_sai_com_zero(monkeypatch, acao):
    """As instrucoes de migracao encadeiam estes comandos: sair com 0 depois de falhar
    faria o proximo passo (index-migrate) rodar com o daemon ainda no ar."""
    monkeypatch.setattr(service, acao, lambda **_k: {"action": acao, "status": "failed"})
    assert _rodar(monkeypatch, acao) != 0


def test_toda_instrucao_de_service_nos_documentos_e_uma_acao_que_existe():
    """Se o README ou o guia citarem `service <algo>`, o algo tem que ser uma acao real."""
    import re
    from pathlib import Path
    raiz = Path(__file__).resolve().parents[1]
    validas = {"install", "uninstall", "status", "stop", "start", "restart"}
    citadas = set()
    for caminho in [raiz / "README.md", raiz / "docs" / "indice-sqlite.md",
                    raiz / "src" / "delegation_core" / "cli.py",
                    raiz / "src" / "delegation_core" / "migracao_indice.py"]:
        for m in re.finditer(r"delegation-core service (\w+)", caminho.read_text(encoding="utf-8")):
            citadas.add(m.group(1))
    assert citadas <= validas, f"documentos citam acoes que o CLI nao tem: {sorted(citadas - validas)}"
