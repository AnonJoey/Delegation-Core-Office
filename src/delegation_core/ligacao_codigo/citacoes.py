"""Quais identificadores de codigo uma nota cita, e a que nos eles se referem.

## Por que existe

As notas deste vault falam de codigo o tempo todo (`gravar_indice()`,
`localqueue.py`, `local_task_status`) e ha 13 grafos de codigo construidos,
mas nada liga um ao outro: de uma nota nao se chega a funcao, e de uma funcao
nao se chega as decisoes e correcoes que a discutiram.

## O que o vault real mostrou (27/09)

- 2.297 identificadores entre crases nas notas vivas; 857 casam com algum no,
  mas 693 desses casam em mais de um grafo: `search`, `graph`, `engine`,
  `description` sao nome de centenas de nos.
- So identificador **distintivo** conta: com `_`, camelCase, `()` no fim, ou
  arquivo com extensao de codigo. Palavra solta nao identifica nada.
- A nota escolhe o grafo por **voto**: cada identificador que casa (em ate
  `max_ambiguo` nos) vota nos grafos onde aparece. Empate vai para o grafo
  cujo nome a nota cita (o mais longo, se cita mais de um); sem citacao, o de
  nome mais curto (`delegation-core` antes de `delegation-core-TEST`). Resultado: 379 ligacoes em 66 notas.
- Funcao citada que nao existe no grafo votado: so 16, quase todas chamadas
  da biblioteca padrao (`is_file()`, `min()`). Pouco demais para virar alerta
  de "codigo que sumiu"; medido e deixado de lado.

## Criterio de lego

Recebe texto e um indice com `buscar(chave) -> list[Alvo]`. Nao sabe o que e
vault, grafo em disco ou MCP.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass

_CRASE = re.compile(r"`([A-Za-z_][\w.]*(?:\(\))?)`")
_ARQUIVO = re.compile(r"\.(py|pyi|ts|tsx|js|jsx|mjs|rs|go|java|kt|cs|c|h|cpp|hpp|rb|php|swift|sh|toml|json|yaml|yml|md)$")
_CAMEL = re.compile(r"[a-z][A-Z]")


@dataclass(frozen=True)
class Alvo:
    grafo: str
    id: str
    rotulo: str
    arquivo: str = ""
    linha: str = ""

    def como_dict(self) -> dict:
        d = asdict(self)
        return {"graph": d["grafo"], "node_id": d["id"], "label": d["rotulo"], "file": d["arquivo"],
                "line": d["linha"]}


def distintivo(c: str) -> bool:
    return c.endswith("()") or "_" in c.strip("_") or bool(_CAMEL.search(c)) or bool(_ARQUIVO.search(c))


def chave_da_citacao(c: str) -> str:
    """`Config.load()` -> `load`; `busca_hibrida.py` -> `busca_hibrida.py`; `x.y.z` -> `z`."""
    if c.endswith("()"):
        c = c[:-2]
    elif _ARQUIVO.search(c):
        return c.rsplit("/", 1)[-1].lower()
    return c.rsplit(".", 1)[-1].lower()


def citacoes(texto: str) -> list[str]:
    vistos: list[str] = []
    for c in _CRASE.findall(texto or ""):
        if distintivo(c) and len(chave_da_citacao(c)) >= 3 and c not in vistos:
            vistos.append(c)
    return vistos


def ligar(texto: str, indice, max_ambiguo: int = 6) -> dict:
    """{"graph": nome ou None, "votes": {...}, "links": [{"cited", "targets": [Alvo...]}]}."""
    cands: dict[str, list] = {}
    votos: Counter = Counter()
    for c in citacoes(texto):
        alvos = indice.buscar(chave_da_citacao(c))
        if not alvos or len(alvos) > max_ambiguo:
            continue
        cands[c] = alvos
        for g in {a.grafo for a in alvos}:
            votos[g] += 1
    if not votos:
        return {"graph": None, "votes": {}, "links": []}
    topo = max(votos.values())
    empatados = sorted((g for g, v in votos.items() if v == topo), key=lambda g: (len(g), g))
    baixo = (texto or "").lower()
    # citado no texto vence; entre citados, o nome mais longo, porque quem
    # escreve `delegation-core-TEST` tambem "cita" `delegation-core`
    citados = sorted((g for g in empatados if g.lower() in baixo), key=lambda g: (-len(g), g))
    grafo = (citados or empatados)[0]
    links = []
    for c, alvos in cands.items():
        doa = [a for a in alvos if a.grafo == grafo]
        if doa:
            links.append({"cited": c, "targets": doa})
    return {"graph": grafo, "votes": dict(votos), "links": links}
