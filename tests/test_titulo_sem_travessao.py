"""O titulo do relatorio de grafo deixa de ter travessao, sem perder as notas antigas.

## Por que mudou

A regra de escrita desta casa proibe travessao em nota do vault, e o
`graphbridge` escrevia `Code Graph Report — <grafo>` como titulo, que vira
nome de arquivo. Medido no vault em 26/09/2026: **361 notas com travessao no
`title:`** e 210 com travessao no nome do arquivo.

## Por que nao bastava trocar o caractere

Porque o travessao fazia parte de um **contrato de parsing**. O
`VaultManager._REPORT_STEM_RE` le o nome do arquivo para classificar a nota
como `kind='generated'` e extrair o nome do grafo. Trocar so o produtor faria
as 13 notas ja gravadas deixarem de ser reconhecidas e caírem no
`scope='notes'`, poluindo a busca padrao do usuario com relatorio de grafo.

E uma divergencia silenciosa de manual: dois lugares que precisam concordar,
em arquivos diferentes, sem nada comparando os dois.

## A migracao

O parser aceita **as duas formas**; o produtor escreve **so a nova**. O
travessao sai da regex quando nao houver mais nota antiga, e nao antes: e
contrato com dado ja gravado, nao preferencia de estilo.

As 13 notas antigas continuam funcionando, e as 9 notas que linkam para elas
tambem. Renomea-las e operacao de dado, com `vault_rename_note`, que repoe os
wikilinks, e fica para o usuario decidir.
"""

from __future__ import annotations

import inspect

import pytest

from delegation_core.vault import VaultManager

TRAVESSAO = "—"


@pytest.mark.parametrize("caminho,esperado", [
    # forma ANTIGA: as 13 notas ja gravadas no vault
    (f"Reference/2026-08-03-Code Graph Report {TRAVESSAO} hermes-agent.md",
     ("generated", "hermes-agent")),
    (f"Reference/2026-08-06-Code Graph Report {TRAVESSAO} delegation-core.md",
     ("generated", "delegation-core")),
    # forma NOVA
    ("Reference/2026-09-26-Code Graph Report - delegation-core.md",
     ("generated", "delegation-core")),
    ("Reference/2026-09-26-Code Graph Report - painel-delegation-core.md",
     ("generated", "painel-delegation-core")),
])
def test_as_duas_formas_classificam_como_gerada(caminho, esperado):
    """A antiga nao pode parar de ser reconhecida: sao 13 notas ja no vault.

    Conferido por mutacao: tirar o travessao da regex derruba os dois
    primeiros casos.
    """
    assert VaultManager.classify_path(caminho) == esperado


def test_nome_de_grafo_com_hifen_dentro_sobrevive():
    """`painel-delegation-core` tem hifen no nome, e o separador virou hifen.

    Se a regex casasse o separador de forma preguicosa no lugar errado, o nome
    do grafo sairia truncado e a busca por `graph=` deixaria de achar.
    """
    k, g = VaultManager.classify_path(
        "Reference/2026-09-26-Code Graph Report - painel-delegation-core.md")
    assert (k, g) == ("generated", "painel-delegation-core")


def test_o_produtor_nao_escreve_mais_travessao():
    """A LIGACAO: a regex aceitar hifen nao adianta se ninguem escrever hifen.

    Conferido por mutacao: devolver o travessao ao `graphbridge` derruba este
    teste.
    """
    from delegation_core import graphbridge

    fonte = inspect.getsource(graphbridge)
    producao = [l for l in fonte.split("\n")
                if "Code Graph Report" in l and "f\"" in l]
    assert producao, "o produtor do titulo sumiu; este teste precisa de outro alvo"
    for linha in producao:
        assert TRAVESSAO not in linha, (
            f"o produtor voltou a escrever travessao: {linha.strip()}")


def test_o_organizer_tambem_nao_rotula_com_travessao():
    """O outro produtor: o label do organizer vira titulo de nota de secao."""
    from delegation_core import organizer

    fonte = inspect.getsource(organizer)
    rotulos = [l for l in fonte.split("\n") if "label = f\"" in l]
    assert rotulos, "o label do organizer sumiu; este teste precisa de outro alvo"
    for linha in rotulos:
        assert TRAVESSAO not in linha, (
            f"o organizer voltou a rotular com travessao: {linha.strip()}")


def test_caminho_que_nao_e_relatorio_continua_nota():
    """Guarda de base: a regex nao pode passar a classificar tudo como gerada."""
    assert VaultManager.classify_path(
        "Reference/2026-09-26-Uma nota qualquer.md")[0] == "note"
    assert VaultManager.classify_path(
        "Reference/Code Graph Report - sem data.md")[0] == "note"
