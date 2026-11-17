"""Vocabulario de erro para a fronteira MCP: o que aconteceu e o que fazer.

## O problema, medido

O `server.py` tem 56 ferramentas MCP e 24 pontos que devolvem erro, todos na
forma `{"error": "<texto livre>"}`. Quem recebe nao consegue separar tres casos
que pedem acoes opostas:

- **nao existe** — repetir nao adianta, mude o pedido
- **falta dependencia opcional** — instalar resolve
- **indisponivel agora** — repetir resolve

Os tres ja convivem no codigo, distinguiveis so pela prosa:

    "web search is disabled. Set web_search_enabled=true in ..."
    'web search backend not installed. Run: pip install "delegation-core[web]"'
    "Note not found: {note_name}"

Um cliente que queira decidir sozinho tem que casar substring de mensagem em
ingles, o que quebra na primeira vez que alguem reescrever a frase.

Isto nao e hipotese. Em 25/09/2026 um `graph_preview` estourou o limite de
silencio do cliente e a resposta nao dizia se o trabalho tinha morrido ou
continuava rodando do outro lado. Descobrir custou duas chamadas extras.

## O desenho, e o que ele NAO faz

Veio do `SupersetErrorType` do superset, quinto maior no por grau daquela base.
Mas veio **recortado**: o superset tem centenas de condicoes de erro em dezenas
de motores de banco, e aqui sao seis classes de erro proprias em quatro
modulos. Copiar a estrutura inteira seria cerimonia sem populacao.

O que foi trazido e so a parte que a medicao justifica: categoria e acionamento
na fronteira MCP.

## Compatibilidade

`error` continua existindo, com exatamente o mesmo texto de antes. Os campos
novos sao **aditivos**, entao nenhum cliente que hoje le `error` quebra. Quem
quiser decidir sozinho passa a ter `error_type` e `retryable`.

## Independencia

Nao importa nada de `delegation_core`. Recebe tudo por argumento e devolve
dicionario. Da para arrancar, testar e trocar sem tocar em vizinho nenhum.
"""

from __future__ import annotations

from enum import Enum


class Categoria(str, Enum):
    """O que aconteceu, na granularidade que muda a acao de quem chamou.

    Herda de `str` para o valor sair direto no JSON sem conversao, e para
    comparacao com string continuar funcionando em quem ja compara.

    Deliberadamente curta. Cada categoria a mais so se justifica quando existir
    um chamador que faria algo diferente por causa dela; categoria que ninguem
    ramifica e ruido com nome bonito.
    """

    #: O alvo nao existe. Repetir com o mesmo pedido nunca vai funcionar.
    NAO_ENCONTRADO = "not_found"

    #: Falta um pacote opcional. A mensagem carrega o comando que resolve.
    DEPENDENCIA_AUSENTE = "missing_dependency"

    #: Existe mas esta desligado por configuracao. Ligar resolve.
    DESLIGADO = "disabled"

    #: O pedido esta malformado. Corrigir o argumento resolve.
    ENTRADA_INVALIDA = "invalid_input"

    #: Existe e esta certo, mas nao da agora. Repetir mais tarde pode resolver.
    INDISPONIVEL = "unavailable"

    #: Nao coube em nenhuma acima. O padrao honesto para `except Exception`,
    #: porque classificar errado e pior que declarar que nao se sabe.
    FALHA = "failure"


#: Quais categorias valem a pena repetir. Esta e a informacao que o chamador
#: realmente quer: tudo o mais ele descobre lendo a mensagem, mas "adianta
#: tentar de novo" e decisao de fluxo e precisa vir estruturada.
_REPETIVEL = frozenset({Categoria.INDISPONIVEL})


def erro(categoria: Categoria, mensagem: str, **extra) -> dict:
    """Monta o envelope de erro que as ferramentas MCP devolvem.

    `mensagem` vai inteira para `error`, sem reescrita, para que a migracao dos
    24 pontos existentes nao mude nenhum texto que alguem ja possa estar lendo.

    `extra` acrescenta campos do proprio contexto, como `job_id` ou `path`.
    Nunca sobrescreve os tres campos fixos: um chamador que passe `error=` por
    engano seria pior que silencioso, seria enganoso.
    """
    envelope = {
        "error": mensagem,
        "error_type": categoria.value,
        "retryable": categoria in _REPETIVEL,
    }
    for chave, valor in extra.items():
        if chave not in envelope:
            envelope[chave] = valor
    return envelope


def nao_encontrado(oque: str, **extra) -> dict:
    """Atalho para o caso mais comum dos 24: alvo inexistente."""
    return erro(Categoria.NAO_ENCONTRADO, oque, **extra)


def dependencia_ausente(mensagem: str, **extra) -> dict:
    """Falta pacote opcional. A mensagem deve conter o comando que resolve.

    Sem o comando dentro, a categoria diz que da para consertar e esconde como,
    que e o pior dos dois mundos.
    """
    return erro(Categoria.DEPENDENCIA_AUSENTE, mensagem, **extra)


def desligado(mensagem: str, **extra) -> dict:
    """Recurso existe e esta desligado por configuracao."""
    return erro(Categoria.DESLIGADO, mensagem, **extra)


def entrada_invalida(mensagem: str, **extra) -> dict:
    """O pedido esta malformado."""
    return erro(Categoria.ENTRADA_INVALIDA, mensagem, **extra)


def indisponivel(mensagem: str, **extra) -> dict:
    """Transitorio. O unico caso em que `retryable` sai verdadeiro."""
    return erro(Categoria.INDISPONIVEL, mensagem, **extra)


def falha(mensagem: str, **extra) -> dict:
    """Nao classificado. O padrao para `except Exception`."""
    return erro(Categoria.FALHA, mensagem, **extra)
