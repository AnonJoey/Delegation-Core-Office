"""O que todo modulo portado do RTK usa: `core::utils` e `core::guard`.

Cada modulo exporta `filtrar(bruto: str, codigo: int) -> str`, a funcao que o
RTK passa ao `runner::run_filtered_with_exit`. O `run` de cada modulo (achar o
binario, montar argumentos) nao e portado: rodar o comando e trabalho do
`delegation-core shell` (execucao.py), igual para todos.
"""

from __future__ import annotations

import math
import re

from ..motor import _ANSI, _linhas as linhas, _truncar as truncate  # noqa: F401  (reexportados)


def strip_ansi(texto: str) -> str:
    return _ANSI.sub("", texto)


def estimate_tokens(texto: str) -> int:
    """`core::guard::estimate_tokens`: bytes UTF-8 / 4, arredondado para cima."""
    return math.ceil(len(texto.encode("utf-8")) / 4)


def never_worse(bruto: str, filtrado: str) -> str:
    """`core::guard::never_worse`: o filtrado so vale se nao custar mais tokens."""
    return bruto if estimate_tokens(filtrado) > estimate_tokens(bruto) else filtrado


def guard_stdout(bruto: str, filtrado: str, clean_outputs: tuple[str, ...] = ()) -> str:
    """`runner::guard_stdout`: saida 'limpa' conhecida passa direto, o resto pela guarda."""
    if trim(bruto) in clean_outputs:
        return filtrado
    return never_worse(bruto, filtrado)


# `char::is_whitespace` do Rust. `str.strip()` tira tambem U+001C..U+001F.
_ESPACOS = "\t\n\x0b\x0c\r \x85\xa0                　"


def trim(s: str) -> str:
    """`str::trim()` do Rust."""
    return s.strip(_ESPACOS)


_RE_ESPACOS = re.compile("[" + re.escape(_ESPACOS) + "]+")


def split_whitespace(s: str) -> list[str]:
    """`str::split_whitespace()` do Rust: sem pedacos vazios."""
    return [p for p in _RE_ESPACOS.split(s) if p]


# ── core::tee em modo sqlite (o padrao do RTK) ───────────────────────────────
# As dicas usam o mesmo armazem e o mesmo hash do execucao.py, portanto o mesmo
# texto do RTK com "rtk" trocado pelo prefixo.

PREFIXO = "delegation-core"


def pelo_filtro(comando: str) -> str:
    """Como a dica manda rodar `comando` pelo filtro: `rtk git diff` no RTK, aqui
    `delegation-core shell 'git diff'` (o delegation-core nao tem um subcomando por ferramenta)."""
    return f"rtk {comando}" if PREFIXO == "rtk" else f"{PREFIXO} shell '{comando}'"


def sem_filtro(comando: str) -> str:
    """Como a dica manda rodar `comando` sem filtro. O RTK reescreve `git show` solto de volta
    para si e por isso manda por `rtk proxy`; o `shell` so entra por comando simples escolhido
    pelo hook, e um `... | tail` nunca e, entao aqui o comando vai como esta."""
    return f"rtk proxy {comando}" if PREFIXO == "rtk" else comando


def tee_and_hint(bruto: str, slug: str, codigo: int, prefixo: str | None = None) -> str | None:
    """`tee::tee_and_hint`: guarda a saida bruta de uma execucao que FALHOU."""
    from ..execucao import MIN_BYTES_FALHA, guardar
    prefixo = prefixo or PREFIXO
    if len(bruto.encode("utf-8")) < MIN_BYTES_FALHA or codigo == 0:
        return None
    g = guardar(bruto, slug, codigo)
    return g and f"[full output: {prefixo} recall {g['hash']}]"


def force_tee_hint(conteudo: str, slug: str, prefixo: str | None = None) -> str | None:
    from ..execucao import guardar
    prefixo = prefixo or PREFIXO
    if not conteudo:
        return None
    g = guardar(conteudo, slug, None)
    return g and f"[full output: {prefixo} recall {g['hash']}]"


def force_tee_tail_hint(conteudo: str, slug: str, deslocamento: int, prefixo: str | None = None) -> str | None:
    from ..execucao import guardar
    prefixo = prefixo or PREFIXO
    if not conteudo:
        return None
    g = guardar(conteudo, slug, None, deslocamento)
    if g and g["hidden_lines"] > 0:
        return f"[+{g['hidden_lines']} hidden: {prefixo} recall {g['hash']}]"
    return None


def print_with_hint(filtrado: str, tee_bruto: str, guard_bruto: str, rotulo: str, codigo: int,
                    prefixo: str | None = None) -> str:
    """`runner::print_with_hint` + `emit_guarded`: o texto que o RTK imprime (sem o \\n final)."""
    dica = tee_and_hint(tee_bruto, rotulo, codigo, prefixo)
    corpo = filtrado if dica is None else f"{filtrado}\n{dica}"
    return never_worse(guard_bruto, corpo)
