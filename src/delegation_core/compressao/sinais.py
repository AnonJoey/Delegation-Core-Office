"""Porte de `crates/headroom-core/src/signals/keyword_detector.rs` (Headroom, Apache 2.0).

Importancia de uma linha por palavra-chave, com fronteira de palavra ASCII e
casamento leftmost-longest sem caixa (ASCII), como o aho-corasick do Rust.
"""

from __future__ import annotations

import re

ERRO = ["error", "exception", "fail", "failed", "failure", "fatal", "critical", "crash", "panic", "abort",
        "timeout", "denied", "rejected"]
AVISO = ["warn", "warning"]
IMPORTANCIA = ["important", "note", "todo", "fixme", "hack", "xxx", "bug", "fix"]
SEGURANCA = ["security", "auth", "password", "secret"]
PREFIXOS_MD = ["# ", "## ", "### ", "#### ", "**", "> "]
PRIORIDADE = {"error": 0.95, "warning": 0.75, "security": 0.85, "importance": 0.6, "markdown": 0.45}


def _automato(entradas: list[tuple[str, list[str]]]):
    cat = {}
    for c, ws in entradas:
        for w in ws:
            cat.setdefault(w.lower(), c)
    padrao = re.compile("|".join(re.escape(w) for w in sorted(cat, key=len, reverse=True)), re.I | re.A)
    return padrao, cat


_UNIVERSAL = _automato([("error", ERRO), ("importance", IMPORTANCIA)])
_AVISO = _automato([("warning", AVISO)])
_SEGURANCA = _automato([("security", SEGURANCA)])


def _palavra(c: str) -> bool:
    return c.isascii() and (c.isalnum() or c == "_")


def _primeira(aut, linha: str) -> str | None:
    padrao, cat = aut
    for m in padrao.finditer(linha):
        s, e = m.start(), m.end()
        if (s == 0 or not _palavra(linha[s - 1])) and (e == len(linha) or not _palavra(linha[e])):
            return cat[m.group(0).lower()]
    return None


def categoria(linha: str, contexto: str = "search") -> str | None:
    """`contexto`: text, search, diff ou log."""
    c = _primeira(_UNIVERSAL, linha)
    if c:
        return c
    if contexto == "diff":
        c = _primeira(_SEGURANCA, linha)
    else:
        c = _primeira(_AVISO, linha)
    if c:
        return c
    if contexto == "text":
        if any(linha.startswith(p) for p in PREFIXOS_MD):
            return "markdown"
    return None
