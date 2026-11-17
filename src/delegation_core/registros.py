"""Ler os logs do proprio delegation-core, filtrados e sem segredo.

## Por que existe

Na noite de 26 para 27/09 os achados de producao sairam de log lido a mao: o
`reindex.log` com linhas duplicadas e intercaladas mostrou dois reindex
concorrentes; o log do daemon mostrou o job que nunca terminava. Um agente sem
shell nao le log nenhum, e com shell le 1 MB de `HTTP Request: POST /mcp`
para achar tres linhas. O grafana tem exploracao de log com filtro
(`public/app/features/explore/Logs`); isto e o minimo disso.

## Regras

- **So fontes conhecidas**, por nome, dentro do diretorio de config. Nunca um
  caminho vindo do chamador: ler arquivo arbitrario por uma ferramenta MCP e
  exatamente o tipo de porta que o `resolve_in_vault` existe para fechar.
- **Ruido fora por padrao**: `HTTP Request:`, `POST /mcp`, `Processing request
  of type` sao mais de 90% do `server.log` e nao dizem nada.
- **Le do fim**: o `llama_cpp.log` tem 4 MB; so o fim interessa.
- **Segredo coberto** pelo pacote `segredos` antes de sair, incluindo o
  `server_token` literal.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from .segredos import redigir

FONTES = {
    "server": "server.log",
    "llama": "llama_cpp.log",
    "reindex": "reindex.log",
    "alertas": "alertas.log",
    "maintenance": "maintenance.log",
    "llama_stop": "llama_stop.log",
}

RUIDO = re.compile(r"HTTP Request:|POST /mcp|GET /api/|Processing request of type|\[\d+B blob data\]|Created new transport with session ID|Terminating session:")
_NIVEL = re.compile(r"\[(DEBUG|INFO|WARNING|ERROR|CRITICAL)\]")
_ORDEM = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}


def _cauda(caminho: Path, max_bytes: int) -> list[str]:
    tam = caminho.stat().st_size
    with caminho.open("rb") as f:
        if tam > max_bytes:
            f.seek(tam - max_bytes)
            f.readline()  # descarta a linha cortada
        return f.read().decode("utf-8", errors="replace").splitlines()


def ler(config_dir: Path, fonte: str, linhas: int = 100, filtro: str = "", nivel: str = "",
        com_ruido: bool = False, max_bytes: int = 2_000_000, segredos_extras: tuple[str, ...] = ()) -> dict:
    if fonte not in FONTES:
        return {"erro": f"fonte desconhecida: {fonte!r}", "fontes": sorted(FONTES)}
    caminho = Path(config_dir) / FONTES[fonte]
    if not caminho.is_file():
        return {"fonte": fonte, "linhas": [], "existe": False}
    try:
        rx = re.compile(filtro, re.IGNORECASE) if filtro else None
    except re.error as e:
        return {"erro": f"filtro invalido: {e}"}
    minimo = _ORDEM.get(nivel.upper(), 0) if nivel else 0
    brutas = _cauda(caminho, max_bytes)
    saida = []
    for ln in brutas:
        if not com_ruido and RUIDO.search(ln):
            continue
        if minimo:
            m = _NIVEL.search(ln)
            if not m or _ORDEM[m.group(1)] < minimo:
                continue
        if rx and not rx.search(ln):
            continue
        saida.append(ln)
    saida = saida[-max(1, min(linhas, 2000)):]
    texto, cobertos = redigir("\n".join(saida), segredos_extras)
    return {"fonte": fonte, "existe": True, "linhas": texto.splitlines() if texto else [],
            "lidas_do_fim": len(brutas), "segredos_cobertos": cobertos,
            "tamanho_arquivo": os.path.getsize(caminho)}
