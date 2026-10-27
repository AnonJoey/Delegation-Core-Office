"""`[[...]]` so e wikilink quando fecha com `]]`, e o `\\|` de tabela nao suja o alvo.

Medido em 19/10/2026 num vault de 39.878 notas: dos 103 links quebrados, 5 nao tinham
nenhuma ocorrencia fechada com `]]` (a expressao antiga so olhava o `[[`). O `[[a\\|b]]` de
uma tabela do Obsidian extraia `a\\`, com a barra invertida, e nunca resolvia.
"""
from delegation_core.notes import _countable_wikilinks


def test_link_sem_fechamento_nao_conta():
    assert _countable_wikilinks("texto [[Nota aberta e mais texto sem fechar") == []


def test_link_que_fecha_so_na_linha_seguinte_nao_conta():
    assert _countable_wikilinks("abre [[Nota\nfecha na outra]] linha") == []


def test_link_fechado_conta_com_alias_e_ancora():
    c = "a [[Nota Um]] b [[Nota Dois|apelido]] c [[Nota Tres#secao]] d [[Nota Quatro#s|ap]]"
    assert _countable_wikilinks(c) == ["Nota Um", "Nota Dois", "Nota Tres", "Nota Quatro"]


def test_pipe_escapado_de_tabela_nao_deixa_barra_no_alvo():
    assert _countable_wikilinks(r"| col | [[Nota X\|apelido]] |") == ["Nota X"]


def test_moeda_continua_valendo_e_shell_continua_fora():
    assert _countable_wikilinks("ver [[R$13,8M]]") == ["R$13,8M"]
    assert _countable_wikilinks('if [[ -f "$x" ]]; then') == []
    assert _countable_wikilinks("anexo [[Pasta/arquivo.pdf]]") == []
