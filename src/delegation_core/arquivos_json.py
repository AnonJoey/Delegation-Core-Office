"""Ler e gravar o estado pequeno em JSON que varios modulos guardam em disco.

Seis modulos tinham a propria copia destas duas funcoes (medido em 06/10/2026
por AST). As copias ja divergiam em detalhe: umas aceitavam so lista, outras so
dict, e nem todas criavam a pasta antes de gravar.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def ler_json(caminho: Path, tipo: type = dict):
    """O conteudo, se for do `tipo` pedido; senao um `tipo()` vazio. Nunca levanta."""
    try:
        dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return tipo()
    return dados if isinstance(dados, tipo) else tipo()


def gravar_json(caminho: Path, dados) -> None:
    """Grava por arquivo temporario e troca, para nunca deixar JSON pela metade."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(caminho.suffix + ".tmp")
    tmp.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, caminho)
