"""Sugestoes de argumento para os prompts MCP (`completion/complete`).

Trazido do REA (`docs/mcp-prompts.md`): as sugestoes saem do estado atual,
sem cache, por prefixo sem caixa e com normalizacao Unicode, sem repeticao e
em ordem estavel. Uma sugestao e so um identificador: nao chama ferramenta
nem amplia nada.

Fontes:
- `note`: nomes de nota do vault (sem `.md`);
- `process_id`: processos ativos, por id ou por nome;
- `question_id`: perguntas em aberto, por id ou pelo texto;
- `folder`: as pastas do vault.
"""

from __future__ import annotations

import os
import unicodedata
from pathlib import Path

MAXIMO = 100


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s).casefold()


def filtrar(candidatos, prefixo: str) -> tuple[list[str], bool]:
    p = _norm(prefixo or "")
    vistos = sorted({c for c in candidatos if c and _norm(c).startswith(p)})
    return vistos[:MAXIMO], len(vistos) > MAXIMO


def notas(cfg) -> list[str]:
    saida = []
    raiz = Path(cfg.vault)
    for pasta in getattr(cfg, "vault_folders", []) or []:
        for dirpath, dirnames, arquivos in os.walk(raiz / pasta):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            saida += [a[:-3] for a in arquivos if a.endswith(".md")]
    return saida


def candidatos(argumento: str, cfg, tracker) -> list[str]:
    if argumento == "note":
        return notas(cfg)
    if argumento == "folder":
        return list(getattr(cfg, "vault_folders", []) or [])
    if argumento == "process_id" and tracker is not None:
        ativos = tracker.list_processes(status="active")
        return [p["id"] for p in ativos] + [p["name"] for p in ativos]
    if argumento == "question_id":
        from .perguntas import listar
        abertas = listar("open")
        return [q["id"] for q in abertas] + [q["question"] for q in abertas]
    return []


def completar(argumento: str, valor: str, cfg, tracker) -> tuple[list[str], bool]:
    try:
        return filtrar(candidatos(argumento, cfg, tracker), valor)
    except Exception:  # noqa: BLE001 - sugestao quebrada vira lista vazia, nunca um id inventado
        return [], False
