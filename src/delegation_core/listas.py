"""Separar uma lista escrita por gente, onde a virgula tambem aparece dentro do item.

## O defeito, reproduzido em 26/09/2026

Tres sitios faziam `texto.split(",")` sem olhar parentese:

- `server.py`, os passos de `process_create`
- `cli.py`, os mesmos passos pela linha de comando
- `session.py`, o `key_decisions` de `export_session`

Entrada:

    Levantar dados (custo, prazo e risco), Analisar, Decidir

Saida de antes, com **quatro** itens e dois deles quebrados ao meio:

    Levantar dados (custo
    prazo e risco)
    Analisar
    Decidir

O vault ja carregava isso em `Fixes/2026-09-10-process_create quebra os passos
em toda virgula`, com a observacao de que nao ha ferramenta para consertar
processo ja criado errado. O defeito seguia vivo nos tres sitios.

## Por que a virgula continua sendo o separador

Trocar por ponto e virgula ou por lista de verdade resolveria melhor, e quebraria
toda chamada existente e todo processo ja gravado. A virgula fica; o que muda e
ela passar a ser separador **so no nivel de fora**.

## Criterio de lego

Recebe uma string e devolve uma lista de strings. Nao sabe o que e processo,
sessao, CLI nem vault. Da para apagar este modulo, voltar ao `split(",")` e o
sistema funciona igual, so quebrando item com parentese de novo.
"""

from __future__ import annotations

#: Pares que suspendem a separacao enquanto estao abertos.
PARES = {"(": ")", "[": "]", "{": "}"}
FECHA = {v: k for k, v in PARES.items()}


def separar(texto: str | None) -> list[str]:
    """Os itens de uma lista separada por virgula, ignorando virgula aninhada.

    Itens vazios sao descartados e as bordas aparadas, que e o que os tres
    sitios ja faziam com `[s.strip() for s in ... if s.strip()]`.

    **Desequilibrio nao pode comer conteudo.** Um texto como `"a), b"` tem um
    fechamento sem abertura, e a profundidade nunca vai abaixo de zero: o pior
    caso vira separar igual ao comportamento antigo, nunca devolver menos texto
    do que entrou. Quem escreve a lista e gente ou modelo, e os dois erram
    parentese.
    """
    if not texto:
        return []

    itens: list[str] = []
    atual: list[str] = []
    pilha: list[str] = []

    for ch in texto:
        if ch in PARES:
            pilha.append(ch)
            atual.append(ch)
        elif ch in FECHA:
            # So desempilha se casar com o que esta aberto. Um fechamento solto
            # e texto, nao estrutura.
            if pilha and pilha[-1] == FECHA[ch]:
                pilha.pop()
            atual.append(ch)
        elif ch == "," and not pilha:
            itens.append("".join(atual))
            atual = []
        else:
            atual.append(ch)

    itens.append("".join(atual))
    return [i.strip() for i in itens if i.strip()]
