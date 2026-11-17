"""Facetas da busca: pasta e intervalo de datas, e a data que uma nota diz ter.

## Por que existe

"O que decidimos na ultima semana" e a pergunta mais comum que a busca nao
sabia responder: ela filtrava por escopo e cliente, nao por pasta nem por data.
O grafana resolve o equivalente com variaveis de painel que filtram toda a
consulta (`public/app/features/variables`); aqui sao tres parametros do
`search_vault`.

## A data de uma nota

Prefixo do nome (`2026-09-27-...`), depois `date:` do frontmatter, por ultimo o
mtime. O mtime vem por ultimo de proposito: os passes de relink e rename de
26/09 reescreveram 528 notas, e por mtime todas pareceriam de ontem. O sonho
usa a mesma funcao, pelo mesmo motivo.

## Criterio de lego

Funcoes puras sobre caminho, cabecalho e mtime. Nao sabe o que e busca.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

_DATA_NOME = re.compile(r"(\d{4}-\d{2}-\d{2})")
_DATA_FM = re.compile(r"^date:\s*[\"']?(\d{4}-\d{2}-\d{2})", re.M)


def data_da_nota(rel: str, cabeca: str, mtime: float) -> str:
    m = _DATA_NOME.search(Path(rel).name)
    if m:
        return m.group(1)
    m = _DATA_FM.search(cabeca or "")
    if m:
        return m.group(1)
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")


def data_valida(texto: str) -> str | None:
    """'2026-09-20' volta igual; qualquer outra coisa, None."""
    try:
        return date.fromisoformat((texto or "").strip()).isoformat()
    except ValueError:
        return None


def dentro(data: str, desde: str = "", ate: str = "") -> bool:
    return (not desde or data >= desde) and (not ate or data <= ate)


def filtrar_por_data(hits: list[dict], raiz: Path, desde: str = "", ate: str = "") -> list[dict]:
    """Mantem os acertos cuja nota tem data no intervalo, e poe a data em cada um."""
    if not desde and not ate:
        return hits
    saida = []
    for h in hits:
        p = Path(raiz) / h.get("path", "")
        try:
            with p.open(encoding="utf-8", errors="ignore") as f:
                cabeca = f.read(600)
            m = p.stat().st_mtime
        except OSError:
            continue
        d = data_da_nota(h.get("path", ""), cabeca, m)
        if dentro(d, desde, ate):
            saida.append({**h, "date": d})
    return saida
