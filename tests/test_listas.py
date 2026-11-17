"""Lista escrita por gente, onde a virgula tambem aparece dentro do item.

## O defeito, reproduzido em 26/09/2026

Tres sitios faziam `texto.split(",")` sem olhar parentese: os passos de
`process_create` no `server.py` e no `cli.py`, e o `key_decisions` de
`export_session` no `session.py`.

Entrada:

    Levantar dados (custo, prazo e risco), Analisar, Decidir

Saida de antes, com quatro itens e dois quebrados ao meio:

    Levantar dados (custo
    prazo e risco)
    Analisar
    Decidir

O vault ja carregava isso em `Fixes/2026-09-10-process_create quebra os passos
em toda virgula`, inclusive com a observacao de que nao ha ferramenta para
consertar processo ja criado errado. O defeito seguia vivo nos tres sitios, e
foi a mineracao do vault pelo modelo local que o trouxe de volta.

## O `key_decisions` importa mais do que parece

Ele e o campo que toda sessao exportada preenche, e uma decisao bem escrita tem
parentese com frequencia: "Modulo X entregue (com teste, mutacao)". Cada uma
dessas virava duas decisoes tortas no vault, para sempre.
"""

from __future__ import annotations

import pytest

from delegation_core.listas import separar


def test_o_defeito_do_vault_reproduzido():
    """O caso exato da nota, que antes dava quatro itens.

    Conferido por mutacao: voltar para `texto.split(",")` derruba este teste.
    """
    assert separar("Levantar dados (custo, prazo e risco), Analisar, Decidir") == [
        "Levantar dados (custo, prazo e risco)",
        "Analisar",
        "Decidir",
    ]


def test_lista_simples_continua_igual():
    """Regressao: a esmagadora maioria das listas nao tem parentese nenhum, e
    elas nao podem mudar de comportamento."""
    assert separar("a, b, c") == ["a", "b", "c"]
    assert separar("Gather data, Analyse, Draft report, Review") == [
        "Gather data", "Analyse", "Draft report", "Review"]


@pytest.mark.parametrize("entrada", ["", None, "   ", ",,,", " , , "])
def test_vazio_devolve_lista_vazia(entrada):
    assert separar(entrada) == []


def test_item_vazio_entre_virgulas_e_descartado():
    """Era o que o `if s.strip()` dos tres sitios ja fazia."""
    assert separar("a, , b") == ["a", "b"]


def test_parenteses_aninhados():
    assert separar("f(g(1, 2), 3), depois") == ["f(g(1, 2), 3)", "depois"]


def test_colchete_e_chave_tambem_suspendem():
    assert separar("lista [1, 2], mapa {a: 1, b: 2}, fim") == [
        "lista [1, 2]", "mapa {a: 1, b: 2}", "fim"]


def test_fechamento_solto_nao_come_conteudo():
    """O teste que guarda o pior modo de falha possivel aqui.

    Quem escreve a lista e gente ou modelo, e os dois erram parentese. Um
    contador ingenuo iria abaixo de zero num `")"` solto e poderia passar a
    tratar o resto do texto como estrutura, engolindo separadores. O pior caso
    tem que ser separar igual ao comportamento antigo, **nunca devolver menos
    texto do que entrou**.

    Conferido por mutacao: desempilhar sem checar se o par casa derruba este
    teste.
    """
    assert separar("a), b") == ["a)", "b"]
    assert separar(") , (") == [")", "("]


def test_abertura_sem_fechamento_nao_perde_o_resto():
    """Desequilibrio do outro lado: o texto continua inteiro, num item so."""
    assert separar("a (b, c") == ["a (b, c"]


def test_o_texto_completo_sempre_sobrevive():
    """Invariante que vale mesmo com parentese torto: nenhum caractere que nao
    seja separador ou borda pode sumir."""
    for entrada in ["a, b", "a (b, c), d", "a), b", "((", "))", "a [b, c) d, e"]:
        junto = "".join(separar(entrada)).replace(" ", "")
        esperado = entrada.replace(" ", "")
        # os separadores de nivel zero somem, o resto nao
        assert len(junto) >= len(esperado) - esperado.count(","), entrada


def test_os_tres_sitios_usam_o_separador():
    """A LIGACAO, e ela e o ponto: a funcao sozinha nao conserta nada.

    Conferido por mutacao: devolver qualquer um dos tres para `split(",")`
    derruba este teste.
    """
    import inspect

    from delegation_core import cli, server, session

    for modulo, nome in ((server, "server"), (cli, "cli"), (session, "session")):
        fonte = inspect.getsource(modulo)
        assert "separar(" in fonte, f"{nome} nao usa o separador"
        assert 'steps.split(",")' not in fonte, f"{nome} ainda divide passos na virgula crua"
        assert 'key_decisions.split(",")' not in fonte, (
            f"{nome} ainda divide decisoes na virgula crua")
