"""Texto do jeito que o Rust o enxerga: espaco, linha e corte em bytes UTF-8.

Os portes do ai-memory (`envelhecimento`, `resumo_inicial`, `passagem`) precisam
dar o mesmo resultado que o original, e o Python e o Rust discordam em quatro coisas
pequenas que mudam a saida:

- **O que e espaco.** `str::trim` e `split_whitespace` do Rust usam a propriedade
  Unicode `White_Space`; `str.strip` e `str.split` do Python usam `str.isspace`,
  que tambem aceita `\\x1c` a `\\x1f`.
- **O que e linha.** `str::lines` quebra em `\\n` e em `\\r\\n`, e deixa um `\\r`
  solto onde esta; `str.splitlines` quebra em onze separadores.
- **O que e letra.** `char::is_alphabetic` do Rust usa a propriedade Unicode `Alphabetic`,
  que inclui numeros-letra e marcas que `str.isalpha` do Python nao aceita (`eh_alfabetico`).
- **O que e tamanho.** `.len()` do Rust conta bytes. Os limites do ai-memory
  (256, 500, 128) sao em bytes, e um corte nao pode partir um caractere.

Sem dependencia de nada do delegation-core.
"""

from __future__ import annotations

import re
from bisect import bisect_right

from .texto_alfabetico import FAIXAS as _FAIXAS_ALFABETICAS

#: Os caracteres com a propriedade Unicode `White_Space` (o que `char::is_whitespace` aceita).
ESPACOS = "\t\n\x0b\x0c\r \x85\xa0  -     　"
_UM_ESPACO = re.compile("[" + ESPACOS + "]")
_ESPACOS = re.compile("[" + ESPACOS + "]+")
_PONTAS = re.compile("^[" + ESPACOS + "]+|[" + ESPACOS + "]+$")
_PONTA_FIM = re.compile("[" + ESPACOS + "]+$")


_INICIOS_ALFABETICOS = tuple(a for a, _ in _FAIXAS_ALFABETICAS)


def eh_alfabetico(c: str) -> bool:
    """`char::is_alphabetic` do Rust: a propriedade Unicode Alphabetic, que e mais larga que `str.isalpha`.

    Inclui os numeros-letra (Ⅶ, 〇) e as marcas Other_Alphabetic. A diferenca vem de uma tabela gerada
    pelo oraculo (`texto_alfabetico`), nao de uma lista escrita a mao.
    """
    if c.isalpha():
        return True
    cp = ord(c)
    i = bisect_right(_INICIOS_ALFABETICOS, cp) - 1
    return i >= 0 and cp <= _FAIXAS_ALFABETICAS[i][1]


def eh_espaco(c: str) -> bool:
    return bool(_UM_ESPACO.fullmatch(c))


def dividir_espacos(texto: str) -> list[str]:
    """`str::split_whitespace`."""
    return [p for p in _ESPACOS.split(texto) if p]


def colapsar_espacos(texto: str) -> str:
    return " ".join(dividir_espacos(texto))


def aparar(texto: str) -> str:
    """`str::trim`."""
    return _PONTAS.sub("", texto)


def aparar_fim(texto: str) -> str:
    """`str::trim_end`."""
    return _PONTA_FIM.sub("", texto)


def linhas(texto: str) -> list[str]:
    """`str::lines`: `\\n` e `\\r\\n` terminam linha, um `\\r` solto fica na linha."""
    if not texto:
        return []
    partes = texto.split("\n")
    terminou = partes[-1] == ""
    if terminou:
        partes.pop()
    saida = []
    for i, p in enumerate(partes):
        sem_terminador = i == len(partes) - 1 and not terminou
        if p.endswith("\r") and not sem_terminador:
            p = p[:-1]
        saida.append(p)
    return saida


def bytes_de(texto: str) -> int:
    return len(texto.encode("utf-8"))


def cortar_em_bytes(texto: str, maximo: int) -> str:
    """O maior prefixo de `texto` com no maximo `maximo` bytes UTF-8, sem partir caractere."""
    if bytes_de(texto) <= maximo:
        return texto
    total = 0
    for i, c in enumerate(texto):
        total += len(c.encode("utf-8"))
        if total > maximo:
            return texto[:i]
    return texto


def truncar_utf8(texto: str, maximo: int) -> str:
    """`truncate_utf8_bytes` do ai-memory: corta com reticencias dentro do limite em bytes."""
    if bytes_de(texto) <= maximo:
        return texto
    if maximo < 3:  # a reticencia ocupa tres bytes
        return ""
    limite = maximo - 3
    total = 0
    fim = 0
    for i, c in enumerate(texto):
        proximo = total + len(c.encode("utf-8"))
        if proximo > limite:
            break
        total = proximo
        fim = i + 1
    return texto[:fim] + "…"
