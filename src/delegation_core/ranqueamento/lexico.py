"""Indice lexico do vault, em SQLite FTS5 com BM25.

## Por que existe

A busca do delegation-core era so densa: `collection.query` sobre embeddings do
BGE. Busca densa acha o que e parecido em sentido e erra o que e identico em
forma: nome de funcao, sigla, numero de versao, id de tarefa, nome de pessoa.
Quem procura `proc_d3941c` ou `embed_device` quer a nota que contem essa
cadeia, e o embedding de uma cadeia sem sentido e ruido.

Busca lexica e o contrario, e as duas erram em lugares diferentes, que e o
que torna a fusao util (ver `fusao.py`). O desenho veio do grafana, que mantem
as duas buscas lado a lado (`pkg/storage/unified/resource/search_hybrid.go`).

## Escolhas

- **FTS5 com `unicode61 remove_diacritics 2`**: o vault e quase todo em
  portugues, e quem digita `contencao` tem que achar `contencao` com cedilha e
  til. Conferido na versao de SQLite que roda aqui (3.53).
- **Tokens da consulta unidos por OR**, cada um entre aspas: BM25 ja premia a
  nota que tem mais deles. Unir por AND (o padrao do FTS5) zera a busca assim
  que uma palavra da pergunta nao aparece na nota, que e o caso comum numa
  pergunta de gente.
- **Titulo pesa mais que corpo** (`bm25(docs, 3.0, 1.0)`), pela mesma razao por
  que o titulo de uma nota e o que a pessoa lembra.
- **Incremental por mtime**: `atualizar` so relê o que mudou, e remove do
  indice o que sumiu do disco.

## Criterio de lego

Recebe caminhos e textos, devolve caminhos e pontuacoes. Nao sabe o que e
config, vault, ChromaDB ou MCP. Apagar este modulo nao muda nada no resto.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from collections.abc import Iterable
from pathlib import Path

#: Palavra que aparece em quase toda nota nao discrimina nada e so custa tempo.
#: Lista curta de proposito: BM25 ja desconta termo comum pelo IDF, isto aqui
#: e so para nao montar consulta com vinte ORs de artigo.
_VAZIAS = frozenset(
    "a o e de do da dos das em no na nos nas um uma uns umas para por com sem "
    "que se ao aos as os ou mas como mais foi ser e the of and to in is for on "
    "it with as at by an be this that from or are was".split()
)

_TOKEN = re.compile(r"[\w][\w.\-]*", re.UNICODE)


def termos_da_consulta(consulta: str, maximo: int = 24) -> list[str]:
    """Os termos que vao para o MATCH, sem repeticao e sem palavra vazia.

    Um termo com ponto ou hifen (`embed_device`, `v0.12`, `bge-m3`) fica
    inteiro entre aspas, e o FTS5 o trata como frase dos pedacos que o
    tokenizador separar. E o caso que a busca densa mais erra.
    """
    vistos: list[str] = []
    for bruto in _TOKEN.findall(consulta or ""):
        t = bruto.strip(".-").lower()
        if len(t) < 2 or t in _VAZIAS or t in vistos:
            continue
        vistos.append(t)
        if len(vistos) >= maximo:
            break
    return vistos


def montar_match(consulta: str) -> str:
    """Expressao MATCH do FTS5, ou "" quando nao sobra termo."""
    termos = termos_da_consulta(consulta)
    return " OR ".join('"' + t.replace('"', '""') + '"' for t in termos)


class IndiceLexico:
    """Um arquivo SQLite com a tabela FTS5 e o mtime de cada documento."""

    def __init__(self, caminho: str | Path):
        self.caminho = Path(caminho)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self._trava = threading.Lock()
        self._con = sqlite3.connect(str(self.caminho), check_same_thread=False)
        self._con.executescript(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS docs USING fts5(
                caminho UNINDEXED, titulo, corpo,
                tokenize = 'unicode61 remove_diacritics 2'
            );
            CREATE TABLE IF NOT EXISTS estado (
                caminho TEXT PRIMARY KEY, mtime REAL NOT NULL, rowid_doc INTEGER NOT NULL
            );
            """
        )

    def fechar(self) -> None:
        with self._trava:
            self._con.close()

    def __len__(self) -> int:
        with self._trava:
            return self._con.execute("SELECT count(*) FROM estado").fetchone()[0]

    def mtimes(self) -> dict[str, float]:
        with self._trava:
            return dict(self._con.execute("SELECT caminho, mtime FROM estado"))

    def gravar(self, caminho: str, mtime: float, titulo: str, corpo: str) -> None:
        """Insere ou substitui um documento."""
        with self._trava, self._con:
            self._remover(caminho)
            cur = self._con.execute(
                "INSERT INTO docs(caminho, titulo, corpo) VALUES (?, ?, ?)",
                (caminho, titulo or "", corpo or ""),
            )
            self._con.execute(
                "INSERT INTO estado(caminho, mtime, rowid_doc) VALUES (?, ?, ?)",
                (caminho, float(mtime), cur.lastrowid),
            )

    def remover(self, caminho: str) -> None:
        with self._trava, self._con:
            self._remover(caminho)

    def _remover(self, caminho: str) -> None:
        linha = self._con.execute(
            "SELECT rowid_doc FROM estado WHERE caminho = ?", (caminho,)
        ).fetchone()
        if linha:
            self._con.execute("DELETE FROM docs WHERE rowid = ?", (linha[0],))
            self._con.execute("DELETE FROM estado WHERE caminho = ?", (caminho,))

    def atualizar(self, documentos: Iterable[tuple[str, float, callable]]) -> dict:
        """Sincroniza com o disco. Cada item e (caminho, mtime, ler), e `ler()`
        so e chamado para o que mudou, devolvendo (titulo, corpo).

        O que estava no indice e nao veio na lista e removido: o chamador passa
        o conjunto inteiro, e o que nao esta nele deixou de existir.
        """
        antes = self.mtimes()
        vistos: set[str] = set()
        gravados = 0
        for caminho, mtime, ler in documentos:
            vistos.add(caminho)
            if antes.get(caminho) == float(mtime):
                continue
            titulo, corpo = ler()
            self.gravar(caminho, mtime, titulo, corpo)
            gravados += 1
        removidos = 0
        for caminho in set(antes) - vistos:
            self.remover(caminho)
            removidos += 1
        return {"gravados": gravados, "removidos": removidos, "total": len(self)}

    def ler(self, caminho: str) -> tuple[str, str] | None:
        """(titulo, corpo) guardados para `caminho`, ou None. O reordenador le daqui
        quando o documento nao e arquivo do vault (pedaco de arquivo ingerido)."""
        with self._trava:
            ln = self._con.execute(
                "SELECT d.titulo, d.corpo FROM estado e JOIN docs d ON d.rowid = e.rowid_doc WHERE e.caminho = ?",
                (caminho,)).fetchone()
        return (ln[0], ln[1]) if ln else None

    def buscar(self, consulta: str, limite: int = 20) -> list[tuple[str, float]]:
        """(caminho, pontuacao) do mais relevante ao menos. Pontuacao maior e melhor.

        O `bm25()` do FTS5 devolve valor negativo, menor e melhor; o sinal e
        trocado aqui para que quem chama nao precise saber disso.
        """
        expr = montar_match(consulta)
        if not expr:
            return []
        with self._trava:
            try:
                linhas = self._con.execute(
                    "SELECT caminho, bm25(docs, 0.0, 3.0, 1.0) AS s FROM docs "
                    "WHERE docs MATCH ? ORDER BY s LIMIT ?",
                    (expr, int(limite)),
                ).fetchall()
            except sqlite3.OperationalError:
                return []
        return [(c, -s) for c, s in linhas]
