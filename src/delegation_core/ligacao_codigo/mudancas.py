"""Quais nos de um grafo um diff tocou, pelas linhas do lado antigo.

## Por que existe

A nota explica por que o codigo e como e. Quando o codigo muda, a nota pode
ficar descrevendo o que nao existe mais, e ninguem sabe quais notas olhar. O
grafo sabe onde cada funcao comeca (`source_location`, so a linha inicial) e
de que commit foi construido (`built_at_commit`); `git diff -U0` desse commit
ate o HEAD da as linhas mudadas exatamente na versao que o grafo conhece.

O trecho de um no vai da linha em que ele comeca ate a linha anterior ao
proximo no do mesmo arquivo. Aproximado (o fim real de uma funcao pode ser
antes, e o que vem depois dela ate o proximo no conta como dela), e por isso
o erro e para o lado de incluir: melhor uma nota a mais para conferir do que
uma nota errada esquecida.

## Criterio de lego

Recebe texto de diff e lista de nos. Nao sabe o que e git, grafo em disco ou vault.
"""

from __future__ import annotations

import re
from collections import defaultdict

_ARQ = re.compile(r"^--- (?:a/)?(.+)$")
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@")


def faixas_do_diff(diff: str) -> dict[str, list[tuple[int, int]]]:
    """{arquivo: [(inicio, fim)]} no lado antigo. Insercao pura vira a linha onde entrou."""
    saida: dict[str, list[tuple[int, int]]] = defaultdict(list)
    atual = None
    for linha in (diff or "").splitlines():
        m = _ARQ.match(linha)
        if m:
            atual = None if m.group(1) == "/dev/null" else m.group(1)
            continue
        m = _HUNK.match(linha)
        if m and atual:
            ini, n = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
            # `-12,0`: nada saiu, algo entrou depois da linha 12
            saida[atual].append((ini, ini) if n == 0 else (ini, ini + n - 1))
    return dict(saida)


def _linha(no: dict) -> int | None:
    m = re.match(r"L(\d+)", str(no.get("source_location") or ""))
    return int(m.group(1)) if m else None


def nos_tocados(nos: list[dict], faixas: dict[str, list[tuple[int, int]]]) -> dict[str, list[tuple[int, int]]]:
    """{id do no: [faixas que caem no trecho dele]}. So no de codigo com linha conhecida."""
    por_arquivo: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    for no in nos:
        if no.get("file_type") != "code":
            continue
        l = _linha(no)
        arq = no.get("source_file")
        if l is None or not arq or arq not in faixas:
            continue
        por_arquivo[arq].append((l, no))
    tocados: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for arq, lista in por_arquivo.items():
        lista.sort(key=lambda x: x[0])
        # o no do arquivo (L1) fica so com o que vem antes do primeiro outro no
        for i, (ini, no) in enumerate(lista):
            fim = lista[i + 1][0] - 1 if i + 1 < len(lista) else 10 ** 9
            for a, b in faixas[arq]:
                if a <= fim and b >= ini:
                    tocados[no["id"]].append((a, b))
    return dict(tocados)
