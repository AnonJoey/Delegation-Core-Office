"""Os modulos Rust do RTK, anotados: o que cada um faz e quem cobre o caso aqui.

O RTK filtra 69 familias de comando com codigo Rust dedicado (`src/cmds/`,
30.626 linhas sem os testes): git, cargo, pytest, docker, aws, mvn... Esses
modulos NAO foram portados; o registro em `rtk_modulos.json` diz, para cada
um, a descricao do proprio arquivo, os comandos que atende e por qual
compressor do delegation-core a saida passa no lugar (`delegation_core_route`:
log, diff, search, text ou auto).

`filter_output` consulta este registro quando nenhum filtro TOML casa: a saida
vai para `compressao.roteador` com o tipo anotado, e a resposta diz qual
modulo do RTK faria o trabalho. Para portar um modulo, troque o `status` e
ligue o codigo; o registro e a lista do que falta.
"""

from __future__ import annotations

import json
import shlex
from functools import lru_cache
from pathlib import Path

ARQUIVO = Path(__file__).parent / "rtk_modulos.json"


@lru_cache(maxsize=1)
def registro() -> list[dict]:
    return json.loads(ARQUIVO.read_text(encoding="utf-8"))["modules"]


def modulo_para(comando: str) -> dict | None:
    """O modulo do RTK que atenderia `comando`, pelo executavel (ou executavel + subcomando)."""
    try:
        partes = shlex.split(comando)
    except ValueError:
        partes = comando.split()
    if not partes:
        return None
    exe = Path(partes[0]).name if not partes[0].startswith("./") else partes[0]
    dois = f"{exe} {partes[1]}" if len(partes) > 1 else ""
    melhor = None
    for m in registro():
        if m["delegation_core_route"] is None:
            continue
        for c in m["commands"]:
            if c == dois:
                return m
            if c == exe and melhor is None:
                melhor = m
    return melhor


def resumo() -> dict:
    mods = registro()
    return {"modules": len(mods), "code_lines": sum(m["code_lines"] for m in mods),
            "ported": sum(1 for m in mods if m["status"] != "not_ported"),
            "by_route": {r: sum(1 for m in mods if m["delegation_core_route"] == r)
                         for r in ("log", "diff", "search", "text", "auto", None)}}
