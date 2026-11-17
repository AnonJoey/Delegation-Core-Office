"""Caminho citado numa nota e conferido contra o disco.

## Por que existe

Nota de decisao e de correcao cita onde as coisas estao: `~/.hermes/config.yaml`,
`/home/usuario/Documents/log.md`, `~/Projects/projeto_antigo`.
A maquina muda e a nota nao. Medido em 27/09 no vault real: 827 caminhos
absolutos entre crases, 277 deles nao existem mais, espalhados em 80 notas.
Uma nota que manda abrir um arquivo que sumiu e estado velho passando por
atual, que e a falha que a memoria deste vault mais registra.

Conferir e mecanico: nao precisa de modelo nenhum, so de `stat`.

## O que conta como referencia

Caminho entre crases que comeca em `~/` ou numa raiz local de disco
(`/home/<usuario desta maquina>/`, `/mnt/`, `/media/`, `/etc/`, `/opt/`,
`/usr/`, `/var/`, `/srv/`). Sufixo de linha (`arquivo.py:490`) e pontuacao
final saem. Molde com `{`, `<`, `*`, `$` ou `...` nao e caminho, e modelo de
caminho: fica de fora, em vez de contar como morto.

A primeira versao contava todo `/algo` entre crases, e o vault real mostrou o
erro: `/loop` e `/gsd-plan-phase` sao comandos, `/api/status` e rota HTTP,
`/Users/saad/` e a casa de outra pessoa em outra maquina. Nenhum deles pode
"morrer" aqui.

## Criterio de lego

Recebe texto e duas funcoes (`existe`, `localizar`). Nao sabe o que e vault,
nota ou MCP; o padrao de `localizar` e nenhum.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field

_CRASE = re.compile(r"`((?:/|~/)[^`\n]+?)`")
_LINHA = re.compile(r":\d+(?::\d+)?$")
_MOLDE = re.compile(r"[{}<>*$|]|\.\.\.|\s")
_RAIZES = ("/mnt/", "/media/", "/etc/", "/opt/", "/usr/", "/var/", "/srv/")
# Disco do Windows visto do WSL, noutra maquina: nao existe aqui por definicao
_ALHEIO = re.compile(r"^/mnt/(?:[a-z]|host|wsl)/")


@dataclass
class Referencia:
    bruto: str
    caminho: str
    existe: bool | None = None
    sugestoes: list[str] = field(default_factory=list)
    ancestral: str = ""

    def como_dict(self) -> dict:
        d = {"path": self.caminho, "exists": self.existe}
        if self.bruto != self.caminho:
            d["cited_as"] = self.bruto
        if self.ancestral:
            d["nearest_existing"] = self.ancestral
        if self.sugestoes:
            d["now_at"] = self.sugestoes
        return d


def _limpar(bruto: str) -> str | None:
    # molde conferido antes de tirar a pontuacao: senao `/usr/share/...` perde
    # os tres pontos e vira `/usr/share/`, um caminho que ninguem citou
    if _MOLDE.search(bruto.strip()):
        return None
    c = bruto.strip().rstrip(".,;:)")
    c = _LINHA.sub("", c)
    if not c or _MOLDE.search(c) or c in ("/", "~/"):
        return None
    return c


def extrair(texto: str, casa: str | None = None) -> list[Referencia]:
    """Caminhos citados, sem repeticao, na ordem em que aparecem. `~` expandido com `casa`."""
    casa = casa if casa is not None else os.path.expanduser("~")
    vistos: dict[str, Referencia] = {}
    for bruto in _CRASE.findall(texto or ""):
        c = _limpar(bruto)
        if c is None:
            continue
        if c.startswith("~/"):
            c = casa.rstrip("/") + c[1:]
        elif not (c.startswith(casa.rstrip("/") + "/") or c.startswith(_RAIZES)) or _ALHEIO.match(c):
            continue
        if c not in vistos:
            vistos[c] = Referencia(bruto=bruto, caminho=c)
    return list(vistos.values())


def _parentesco(a: str, b: str) -> int:
    """Quantos componentes finais os dois caminhos tem em comum."""
    pa, pb = a.rstrip("/").split("/"), b.rstrip("/").split("/")
    n = 0
    while n < min(len(pa), len(pb)) and pa[-1 - n] == pb[-1 - n]:
        n += 1
    return n


def verificar(refs: list[Referencia], existe: Callable[[str], bool] = os.path.exists,
              localizar: Callable[[str], list[str]] | None = None, sugestoes: int = 3,
              minimo: int = 3) -> list[Referencia]:
    """Marca `existe`; para as mortas, sugere onde um arquivo com o mesmo nome esta agora.

    Sugestao vem so de `localizar(nome)`, e so a que existe de fato e divide
    com o caminho citado os `minimo` componentes finais. So o nome dava lixo
    no vault real: `server.py` de um projeto apagado "estava agora" em
    `/usr/lib/python3.14/http/`; com nome e pasta, `.../bin/java` do curseforge
    "estava" em `/usr/bin/java`. Tres componentes nao casam por acaso.

    `ancestral` e a pasta mais funda do caminho citado que ainda existe: diz
    ate onde a nota continua certa, sem adivinhar nada.
    """
    for r in refs:
        r.existe = bool(existe(r.caminho))
        if r.existe:
            continue
        pai = os.path.dirname(r.caminho.rstrip("/"))
        while pai and pai != "/" and not existe(pai):
            pai = os.path.dirname(pai)
        r.ancestral = pai if pai and pai != "/" else ""
        if localizar is None:
            continue
        nome = os.path.basename(r.caminho.rstrip("/"))
        if not nome:
            continue
        try:
            achados = [p for p in localizar(nome)
                       if p != r.caminho and _parentesco(p, r.caminho) >= minimo and existe(p)]
        except Exception:  # noqa: BLE001 - busca por nome e opcional
            achados = []
        achados.sort(key=lambda p: (-_parentesco(p, r.caminho), len(p)))
        r.sugestoes = achados[:sugestoes]
    return refs
