"""Fatos duraveis de um texto: caminhos, URLs, codigos de erro, identificadores. Sem modelo.

Porte de `crates/ai-memory-consolidate/src/keep_tokens.rs` do ai-memory (MIT, Fabio Akita).

Quando uma nota fria e compactada em vez de apagada, a prosa vai embora e o que sobra
tem que ser o que uma busca futura procuraria: os caminhos de arquivo, as URLs, os
codigos de erro, os identificadores. Aqui eles saem so por expressao regular, na mesma
ordem do original (as classes de mais sinal primeiro, para o corte do limite guardar as
melhores), sem repeticao, e com limite de quantidade e de tamanho.

Duas diferencas de dialeto, tratadas aqui para o resultado bater com o do Rust:
`\\s` do Python aceita `\\x1c` a `\\x1f` e o do Rust nao (a classe de espaco e escrita
por extenso), e os tamanhos sao em bytes UTF-8, como o `.len()` do Rust.

Pacote independente: so a biblioteca padrao e `texto_bytes`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..texto_bytes import ESPACOS, aparar, aparar_fim, bytes_de, cortar_em_bytes

MAX_TOKENS = 48
MAX_TOKEN_BYTES = 128
MIN_TOKEN_BYTES = 2

_E = ESPACOS
_URL = r"https?://[^" + _E + r"<>()\[\]\"'`]+"
_EXT = r"(?:rs|md|toml|sql|json|ya?ml|sh|py|js|ts|tsx|jsx|rb|go|c|h|cc|cpp|hpp|txt|lock|cfg|ini|env|xml|html|css|proto)"
_ARQUIVO_SOLTO = r"\b[A-Za-z0-9_.-]+\." + _EXT + r"\b"
_HTTP = r"\bHTTP[" + _E + r"]?\d{3}\b"
_CONSTANTE = r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b"


@dataclass(frozen=True)
class _Padrao:
    re: re.Pattern
    grupo: int
    linha: bool


def _p(padrao: str, grupo: int = 0, linha: bool = False) -> _Padrao:
    return _Padrao(re.compile(padrao), grupo, linha)


#: Classes minadas, na ordem em que entram.
PADROES = [
    _p(_URL),
    _p(r"\b(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.[A-Za-z0-9]+\b"),
    _p(_ARQUIVO_SOLTO),
    _p(r"\bE\d{2,4}\b"),
    _p(_HTTP),
    _p(r"`([^`\n]{1,120})`", 1),
    _p(_CONSTANTE),
    _p(r"\b(?:[a-z][a-z0-9]*_[a-z0-9_]+|[a-z][a-z0-9]*[A-Z][A-Za-z0-9]*)\b"),
]

#: Literais uteis quando uma observacao ficou fora de um prompt: diagnosticos, versoes, IPs.
PADROES_RESIDUO = [
    _p(
        r"(?m)((?:\berror(?:\[E\d{2,4}\])?: |\bERROR: |\bERRO: |\bErro: |\bERR! |\b\w*(?:Error|Exception): "
        r"|\bpanicked at |\bFAILED\b|\bfatal: |\bFATAL: |Traceback \(most recent call last\))"
        r"[^\n\r  ]*)",
        1, True),
    _p(_URL),
    _p(r"(?:/|\b)(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.[A-Za-z0-9]+\b"),
    _p(_ARQUIVO_SOLTO),
    _p(r"\bE\d{2,4}\b"),
    _p(_HTTP),
    _p(r"\b\d{1,3}(?:\.\d{1,3}){3}\b|\bv?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?\b"),
    _p(_CONSTANTE),
]


def _aparar_token(bruto: str) -> str:
    """Tira a pontuacao que a regex engoliu nas pontas (URL no fim de frase, caminho entre parenteses)."""
    return aparar(bruto).strip(".,;:)(\"'<>`")


def _cortar_linha(bruto: str) -> str:
    bruto = aparar(bruto)
    if bytes_de(bruto) <= MAX_TOKEN_BYTES:
        return bruto
    return aparar_fim(cortar_em_bytes(bruto, MAX_TOKEN_BYTES))


def _minerar(padroes: list[_Padrao], corpo: str, maximo: int) -> list[str]:
    if maximo == 0:
        return []
    vistos: set[str] = set()
    saida: list[str] = []
    for pad in padroes:
        for m in pad.re.finditer(corpo):
            texto = m.group(pad.grupo)
            if texto is None:
                continue
            token = _cortar_linha(texto) if pad.linha else _aparar_token(texto)
            n = bytes_de(token)
            if n < MIN_TOKEN_BYTES or n > MAX_TOKEN_BYTES:
                continue
            if token not in vistos:
                vistos.add(token)
                saida.append(token)
                if len(saida) >= maximo:
                    return saida
    return saida


def minerar_fatos(corpo: str) -> list[str]:
    """`mine_keep_tokens`. Vazio para prosa pura: sinal de que descartar o corpo nao perde nada."""
    return _minerar(PADROES, corpo, MAX_TOKENS)


def residuo(corpo: str, maximo: int) -> list[str]:
    """`mine_residue_tokens`: diagnosticos literais de um texto cortado, com limite de quantidade."""
    return _minerar(PADROES_RESIDUO, corpo, maximo)
