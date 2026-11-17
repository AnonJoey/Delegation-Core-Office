"""Ler so o comeco de uma nota e separar o frontmatter dele, sem modelo e sem indice.

Varreduras que olham muitas notas (envelhecimento, autoridade, resumo de inicio de sessao) nao
precisam do corpo inteiro: o frontmatter esta no comeco. Ler 8 KiB de cada nota em vez do arquivo
inteiro e o que deixa uma varredura de milhares de notas barata. Um frontmatter que passa disso,
ou que o YAML nao entende, conta como ausente: e melhor perder uma etiqueta que quebrar a varredura.
"""

from __future__ import annotations

import re
from pathlib import Path

CABECA_BYTES = 8192
_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def ler_cabeca(caminho: Path, n: int = CABECA_BYTES) -> str | None:
    try:
        with Path(caminho).open("rb") as f:
            return f.read(n).decode("utf-8", errors="ignore")
    except OSError:
        return None


def frontmatter_de(texto: str) -> dict:
    """O frontmatter como dicionario; `{}` se nao houver, se estiver quebrado ou se nao for um mapa."""
    m = _FRONTMATTER.match(texto)
    if m is None:
        return {}
    try:
        import yaml

        fm = yaml.safe_load(m.group(1))
    except Exception:  # noqa: BLE001 - frontmatter quebrado conta como ausente
        return {}
    return fm if isinstance(fm, dict) else {}


def dividir(texto: str) -> tuple[dict, str]:
    """(frontmatter, corpo) de uma nota inteira."""
    m = _FRONTMATTER.match(texto)
    if m is None:
        return {}, texto
    return frontmatter_de(texto), texto[m.end():]
