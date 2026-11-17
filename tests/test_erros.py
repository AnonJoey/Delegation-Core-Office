"""O vocabulario de erro da fronteira MCP.

O que estes testes guardam nao e a existencia das funcoes, e duas promessas
que, quebradas, so apareceriam em producao:

1. **Compatibilidade.** `error` continua com o texto exato de antes. Os 24
   pontos migrados nao podem mudar nenhuma mensagem que alguem ja leia.
2. **Acionamento.** `retryable` so e verdadeiro onde repetir realmente pode
   resolver. Um `retryable` generoso faz cliente educado entrar em laco.
"""

from __future__ import annotations

import json

import pytest

from delegation_core.erros import (
    Categoria,
    dependencia_ausente,
    desligado,
    entrada_invalida,
    erro,
    falha,
    indisponivel,
    nao_encontrado,
)


def test_a_mensagem_sai_intacta_no_campo_error():
    """A promessa de compatibilidade: nenhum texto e reescrito.

    Os 24 pontos do server.py migram um a um, e um cliente que hoje casa a
    mensagem nao pode quebrar por causa da migracao.
    """
    texto = "Note not found: 2026-09-01-alguma nota"
    assert nao_encontrado(texto)["error"] == texto


def test_so_o_transitorio_e_repetivel():
    """`retryable` existe para o chamador decidir se insiste.

    Marcar como repetivel um erro que nunca vai passar poe o cliente em laco,
    e e pior que nao informar nada.
    """
    assert indisponivel("o modelo local esta carregando")["retryable"] is True

    for construtor in (nao_encontrado, dependencia_ausente, desligado,
                       entrada_invalida, falha):
        assert construtor("x")["retryable"] is False, construtor.__name__


def test_os_tres_casos_que_a_prosa_nao_separava():
    """O motivo de este modulo existir, com os textos reais do server.py.

    Antes, os tres saiam como `{"error": "<texto>"}` e so davam para separar
    casando substring em ingles. Cada um pede uma acao diferente.
    """
    ligar = desligado("web search is disabled. Set web_search_enabled=true in ...")
    instalar = dependencia_ausente(
        'web search backend not installed. Run: pip install "delegation-core[web]"')
    inexistente = nao_encontrado("Note not found: alguma")

    tipos = {e["error_type"] for e in (ligar, instalar, inexistente)}
    assert len(tipos) == 3, "os tres casos tem que ser distinguiveis sem ler prosa"


def test_contexto_extra_entra_no_envelope():
    e = nao_encontrado("Job 'abc' nao existe", job_id="abc", task="graph_build")
    assert e["job_id"] == "abc"
    assert e["task"] == "graph_build"


def test_extra_nao_sobrescreve_os_campos_fixos():
    """Um `error=` passado por engano seria pior que silencioso, seria enganoso:
    a mensagem diria uma coisa e o tipo outra."""
    e = erro(Categoria.NAO_ENCONTRADO, "a verdadeira",
             error="a falsa", error_type="mentira", retryable=True)
    assert e["error"] == "a verdadeira"
    assert e["error_type"] == "not_found"
    assert e["retryable"] is False


def test_o_envelope_sobrevive_a_ida_e_volta_por_json():
    """As ferramentas MCP devolvem `json.dumps` do dicionario. Uma categoria
    que nao serializasse quebraria so em producao."""
    e = indisponivel("tente de novo", job_id="x")
    assert json.loads(json.dumps(e)) == e


def test_a_categoria_compara_como_string():
    """Herdar de `str` existe para quem ja compara com literal continuar
    funcionando, e para o valor sair direto no JSON sem conversao."""
    assert Categoria.NAO_ENCONTRADO == "not_found"
    assert nao_encontrado("x")["error_type"] == "not_found"


@pytest.mark.parametrize("construtor,esperado", [
    (nao_encontrado, "not_found"),
    (dependencia_ausente, "missing_dependency"),
    (desligado, "disabled"),
    (entrada_invalida, "invalid_input"),
    (indisponivel, "unavailable"),
    (falha, "failure"),
])
def test_cada_atalho_produz_a_propria_categoria(construtor, esperado):
    assert construtor("m")["error_type"] == esperado
