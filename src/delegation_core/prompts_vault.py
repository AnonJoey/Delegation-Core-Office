"""Prompts MCP: o cliente mostra como comando (no Claude Code, `/mcp__delegation-core__brief`).

## Por que existe

Tudo que o delegation-core sabe de "o que precisa de atencao" chega ao agente
por hook (so Claude Code) ou pelo `heartbeat` (so quando o agente chama). A
pessoa nao tinha como pedir isso ela mesma, em qualquer cliente. Prompt MCP e
o jeito do protocolo de oferecer um comando a pessoa: o cliente lista, ela
escolhe, e o texto vai para a conversa.

Nao marca nada como visto: pedido explicito mostra tudo.

## Criterio de lego

Funcoes puras sobre dados ja gravados (`atencao.json`, resumo dos processos,
pasta de decisoes). Quem registra no MCP e o `server.py`.
"""

from __future__ import annotations

import json
import time
from pathlib import Path


def decisoes_recentes(vault: Path, dias: int = 7, limite: int = 10, pasta: str = "Decisions") -> list[str]:
    base = Path(vault) / pasta
    if not base.is_dir():
        return []
    corte = time.time() - dias * 86400
    notas = [p for p in base.rglob("*.md") if p.stat().st_mtime >= corte]
    notas.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [str(p.relative_to(vault)) for p in notas[:limite]]


def brief(config_dir: Path, vault: Path, processos: dict | None) -> str:
    linhas = ["Here is the current state of the delegation-core vault. Summarize it for the user in a few "
              "short lines, most important first, and offer to act on any item.", ""]
    try:
        at = json.loads((Path(config_dir) / "atencao.json").read_text(encoding="utf-8"))
        itens = at.get("itens") or []
    except (OSError, ValueError):
        itens = []
    linhas.append(f"## Needs attention ({len(itens)})")
    linhas += [f"- [{i.get('tipo')}] {i.get('texto')} (look with: {i.get('dica')})" for i in itens[:15]] or ["- nothing"]
    if len(itens) > 15:
        linhas.append(f"- ...and {len(itens) - 15} more")
    linhas += ["", "## Active processes"]
    ativos = (processos or {}).get("active") or []
    linhas += [f"- {p['name']} ({p['steps_done']} steps, updated {p['updated']}, id {p['id']})" for p in ativos] \
        or ["- none"]
    linhas += ["", "## Decisions written in the last 7 days"]
    linhas += [f"- {d}" for d in decisoes_recentes(vault)] or ["- none"]
    return "\n".join(linhas)


def perguntar(pergunta: str) -> str:
    return (f"Answer this from the user's vault: {pergunta}\n\n"
            "Call ask_vault with the question first. Present only the claims it returns, each with its source "
            "note and quote. If found is false, say the vault does not have it and offer search_vault. "
            "If a claim carries source_superseded_by, say that a newer note updated it.")
