"""Porte de outliers.rs e anchors.rs do SmartCrusher (Headroom, Apache 2.0):
itens fora do padrao, itens com palavra de erro, e ancoras extraidas da pergunta."""

from __future__ import annotations

import math
import re

from .base import ERROR_KEYWORDS
from .jsonv import Num, dumps


def _b(s: str) -> bytes:
    return s.encode("utf-8")


# ── outliers.rs ─────────────────────────────────────────────────────────────

def detect_structural_outliers(items: list) -> list[int]:
    if len(items) < 5:
        return []
    contagem: dict[str, int] = {}
    for it in items:
        if isinstance(it, dict):
            for k in it:
                contagem[k] = contagem.get(k, 0) + 1
    n = len(items)
    comuns = {k for k, c in contagem.items() if c >= n * 0.8}
    raros = {k for k, c in contagem.items() if c < n * 0.2}
    fora = set()
    for i, it in enumerate(items):
        if isinstance(it, dict) and any(k in raros for k in it):
            fora.add(i)
    fora.update(detect_rare_status_values(items, comuns))
    return sorted(fora)


def _texto(v) -> str:
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, Num):
        return v.raw
    if isinstance(v, str):
        return v
    return dumps(v)


def detect_rare_status_values(items: list, comuns: set) -> list[int]:
    fora: list[int] = []
    for campo in sorted(comuns, key=_b):
        valores = [it[campo] for it in items if isinstance(it, dict) and campo in it]
        unicos = {_texto(v) for v in valores if v is not None}
        if not 2 <= len(unicos) <= 50:
            continue
        contagem: dict[str, int] = {}
        for v in valores:
            k = "__none__" if v is None else _texto(v)
            contagem[k] = contagem.get(k, 0) + 1
        if not contagem:
            continue
        ordem = sorted(contagem.items(), key=lambda kv: (-kv[1], _b(kv[0])))
        limiar = math.ceil(len(valores) * 0.8)
        acumulado, topo = 0, set()
        for valor, c in ordem:
            acumulado += c
            topo.add(valor)
            if acumulado >= limiar:
                break
        if len(topo) > 5:
            continue
        for i, it in enumerate(items):
            if not isinstance(it, dict) or campo not in it:
                continue
            v = it[campo]
            if ("__none__" if v is None else _texto(v)) not in topo:
                fora.append(i)
    return fora


def detect_error_items_for_preservation(items: list, item_strings: list[str] | None = None) -> list[int]:
    saida = []
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        s = (item_strings[i] if item_strings is not None and i < len(item_strings) else dumps(it)).lower()
        if any(k in s for k in ERROR_KEYWORDS):
            saida.append(i)
    return saida


# ── anchors.rs ──────────────────────────────────────────────────────────────

_UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
_NUM_ID = re.compile(r"\b\d{4,}\b")
_HOST = re.compile(r"\b[a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z0-9][-a-zA-Z0-9]*(?:\.[a-zA-Z]{2,})?\b")
_ASPAS = re.compile(r"""['"]([^'"]{1,50})['"]""")
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
_FALSOS_HOST = ("e.g", "i.e", "etc.")


def extract_query_anchors(texto: str) -> set[str]:
    a: set[str] = set()
    if not texto:
        return a
    a.update(m.group(0).lower() for m in _UUID.finditer(texto))
    a.update(m.group(0) for m in _NUM_ID.finditer(texto))
    for m in _HOST.finditer(texto):
        lc = m.group(0).lower()
        if lc not in _FALSOS_HOST:
            a.add(lc)
    for m in _ASPAS.finditer(texto):
        if len(m.group(1).strip().encode("utf-8")) >= 2:
            a.add(m.group(1).lower())
    a.update(m.group(0).lower() for m in _EMAIL.finditer(texto))
    return a


def python_repr(v) -> str:
    if v is None:
        return "None"
    if v is True:
        return "True"
    if v is False:
        return "False"
    if isinstance(v, Num):
        return v.raw
    if isinstance(v, str):
        return "'" + v + "'"
    if isinstance(v, list):
        return "[" + ", ".join(python_repr(x) for x in v) + "]"
    return "{" + ", ".join(f"'{k}': {python_repr(x)}" for k, x in v.items()) + "}"


def item_matches_anchors(item, ancoras: set[str]) -> bool:
    if not ancoras:
        return False
    s = python_repr(item).lower()
    return any(a in s for a in ancoras)
