"""Indice vetorial em SQLite com busca exata em numpy.

Existe porque o ChromaDB 1.5.9 (a ultima do PyPI) tem defeitos de corrupcao
abertos no upstream (issues 7510, 7238 e 7678) e nenhuma correcao publicada:
com um processo segurando o indice aberto, outro que abre e escreve cai com
SIGSEGV, e o indice perde linhas sem aviso. Medido em 07/10/2026, no cenario
"longevo" do m6: 7 de 10 processos cairam e o indice terminou com 34.300
linhas das 41.000 esperadas. O mesmo cenario, neste modulo: nenhuma queda e
53.301 de 53.301 (ver docs/substituto-do-chromadb.md).

O que este modulo e: a fachada do ChromaDB que o resto do codigo usa
(`get_or_create_collection`, `upsert`, `get`, `query`, `delete`, `count`,
`modify`), sobre um unico arquivo SQLite em WAL. O chunk (texto, metadados e
vetor) mora numa linha; a busca e o produto interno exato sobre uma matriz
normalizada que cada processo mantem em memoria e atualiza sozinho.

Decisoes que merecem o porque:

- **Exato, sem ANN.** Com 41 mil vetores de 1024 dimensoes a varredura custa
  10 a 20 ms. Um indice aproximado traria de volta o que causou o problema:
  um componente nativo com estado proprio em disco, fora da transacao.
- **A transacao e do SQLite.** `kill -9` no meio de uma escrita desfaz a
  transacao inteira; nao existe estado em que o texto esteja gravado e o vetor
  nao. Os testes matam escritores de verdade.
- **Varios processos.** Cada escrita registra o que mudou em `mudancas`. Quem
  consulta compara o ultimo numero que viu com o atual (uma leitura) e aplica
  so a diferenca na propria matriz. Nao ha reabertura de cliente nem
  recarga total, que e o que o `_reload_if_disk_changed` do Chroma precisava.
- **Mesmas respostas que o Chroma.** O comportamento nas bordas foi medido no
  Chroma 1.5.9 e copiado, nao suposto: `$ne` casa com chave ausente; `True`
  nao e igual a `1`; `upsert` mescla os metadados e mantem o documento quando
  ele nao e passado; `get(ids=...)` devolve na ordem de armazenamento, nao na
  do pedido; `add` de um id existente e ignorado.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable

import numpy as np

logger = logging.getLogger("indice_sqlite")

NOME_DO_ARQUIVO = "indice.db"
VERSAO_DO_ESQUEMA = 1
#: Quantas mudancas o registro guarda antes de podar. Quem estiver mais de
#: `MUDANCAS_MAXIMAS` atras recarrega a colecao inteira em vez de aplicar a
#: diferenca, o que e correto, so mais lento.
MUDANCAS_MAXIMAS = 200_000
ESPERA_DO_BANCO_MS = 60_000
_AUSENTE = object()

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS esquema (chave TEXT PRIMARY KEY, valor TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS colecoes (
    nome TEXT PRIMARY KEY, metadata TEXT NOT NULL DEFAULT '{}', dim INTEGER);
CREATE TABLE IF NOT EXISTS chunks (
    rid INTEGER PRIMARY KEY AUTOINCREMENT,
    col TEXT NOT NULL, id TEXT NOT NULL,
    doc TEXT, meta TEXT NOT NULL DEFAULT '{}', vec BLOB NOT NULL,
    UNIQUE (col, id));
CREATE TABLE IF NOT EXISTS mudancas (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    col TEXT NOT NULL, rid INTEGER NOT NULL, op TEXT NOT NULL);
"""


_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    doc, content='chunks', content_rowid='rid', tokenize='trigram');
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, doc) VALUES (new.rid, new.doc); END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, doc) VALUES ('delete', old.rid, old.doc); END;
CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE OF doc ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, doc) VALUES ('delete', old.rid, old.doc);
    INSERT INTO chunks_fts(rowid, doc) VALUES (new.rid, new.doc); END;
"""


class IndiceSqliteErro(ValueError):
    """Entrada invalida para o indice (dimensao, ids repetidos, filtro)."""


# ── filtros `where` ──────────────────────────────────────────────────────────

def _numero(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _igual(a: Any, b: Any) -> bool:
    """Igualdade com os tipos do Chroma: bool, numero e texto nao se misturam."""
    if a is _AUSENTE:
        return False
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if _numero(a) and _numero(b):
        return a == b
    return isinstance(a, str) and isinstance(b, str) and a == b


def _ordem(a: Any, b: Any, op: str) -> bool:
    if not (_numero(a) and _numero(b)):
        return False
    return {"$gt": a > b, "$gte": a >= b, "$lt": a < b, "$lte": a <= b}[op]


def _predicado(where: dict) -> Callable[[dict], bool]:
    """Compila um `where` do Chroma numa funcao sobre o dict de metadados."""
    if not isinstance(where, dict) or len(where) != 1:
        raise IndiceSqliteErro(
            f"o filtro precisa ter exatamente um operador ou uma chave, veio {where!r}")
    (chave, valor), = where.items()
    if chave in ("$and", "$or"):
        if not isinstance(valor, list) or not valor:
            raise IndiceSqliteErro(f"{chave} precisa de uma lista nao vazia")
        subs = [_predicado(w) for w in valor]
        if chave == "$and":
            return lambda m: all(p(m) for p in subs)
        return lambda m: any(p(m) for p in subs)
    if chave.startswith("$"):
        raise IndiceSqliteErro(f"operador {chave} nao suportado")
    if isinstance(valor, dict):
        if len(valor) != 1:
            raise IndiceSqliteErro(f"um operador por chave, veio {valor!r}")
        (op, alvo), = valor.items()
        if op == "$eq":
            return lambda m: _igual(m.get(chave, _AUSENTE), alvo)
        if op == "$ne":
            return lambda m: not _igual(m.get(chave, _AUSENTE), alvo)
        if op in ("$in", "$nin"):
            if not isinstance(alvo, list):
                raise IndiceSqliteErro(f"{op} precisa de uma lista")
            if op == "$in":
                return lambda m: any(_igual(m.get(chave, _AUSENTE), x) for x in alvo)
            return lambda m: not any(_igual(m.get(chave, _AUSENTE), x) for x in alvo)
        if op in ("$gt", "$gte", "$lt", "$lte"):
            return lambda m: _ordem(m.get(chave, _AUSENTE), alvo, op)
        raise IndiceSqliteErro(f"operador {op} nao suportado")
    return lambda m: _igual(m.get(chave, _AUSENTE), valor)


# ── conexao ──────────────────────────────────────────────────────────────────

class _Conexao(sqlite3.Connection):
    tem_fts = False

def _conectar(caminho: Path) -> sqlite3.Connection:
    c = sqlite3.connect(str(caminho), timeout=ESPERA_DO_BANCO_MS / 1000,
                        isolation_level=None, factory=_Conexao)
    c.execute(f"PRAGMA busy_timeout={ESPERA_DO_BANCO_MS}")
    c.execute("PRAGMA journal_mode=WAL")
    # NORMAL em WAL: um kill -9 do processo nunca perde nem corrompe; so uma
    # queda de energia pode perder as ultimas transacoes, e o indice e
    # derivado dos markdowns, que continuam sendo a fonte da verdade.
    c.execute("PRAGMA synchronous=NORMAL")
    c.executescript(_ESQUEMA)
    try:
        c.executescript(_FTS)
        c.tem_fts = True
    except sqlite3.OperationalError as e:
        # Um sqlite sem FTS5 ou sem o tokenizador trigram (anterior a 3.34):
        # a busca por conteudo fica desligada, o resto funciona.
        logger.warning("FTS5 trigram indisponivel (%s): where_document e busca de texto desligados", e)
        c.tem_fts = False
    c.execute("INSERT OR IGNORE INTO esquema VALUES ('versao', ?)", (str(VERSAO_DO_ESQUEMA),))
    return c


# ── colecao ──────────────────────────────────────────────────────────────────

class _Cache:
    """A colecao em memoria: ids, metadados e a matriz normalizada."""

    def __init__(self, dim: int):
        self.dim = dim
        self.n = 0
        self.rids = np.zeros(1024, dtype=np.int64)
        self.vivo = np.zeros(1024, dtype=bool)
        self.matriz = np.zeros((1024, dim), dtype=np.float32)
        self.ids: list[str | None] = []
        self.metas: list[dict | None] = []
        self.pos: dict[int, int] = {}       # rid -> posicao
        self.seq = 0
        self.mortos = 0
        self.versao = 0                     # muda a cada alteracao (invalida mascaras)

    def _crescer(self) -> None:
        cap = len(self.rids) * 2
        self.rids = np.resize(self.rids, cap)
        self.vivo = np.concatenate([self.vivo, np.zeros(cap - len(self.vivo), dtype=bool)])
        nova = np.zeros((cap, self.dim), dtype=np.float32)
        nova[:self.n] = self.matriz[:self.n]
        self.matriz = nova

    @staticmethod
    def _normalizar(blob: bytes, dim: int) -> np.ndarray:
        v = np.frombuffer(blob, dtype=np.float32, count=dim)
        norma = float(np.linalg.norm(v))
        return v / norma if norma > 0 else v

    def por(self, rid: int, id_: str, meta: dict, blob: bytes) -> None:
        p = self.pos.get(rid)
        if p is None:
            if self.n == len(self.rids):
                self._crescer()
            p = self.n
            self.n += 1
            self.ids.append(id_)
            self.metas.append(meta)
            self.pos[rid] = p
            self.rids[p] = rid
            self.vivo[p] = True
        else:
            self.ids[p] = id_
            self.metas[p] = meta
            if not self.vivo[p]:
                self.vivo[p] = True
                self.mortos -= 1
        self.matriz[p] = self._normalizar(blob, self.dim)
        self.versao += 1

    def tirar(self, rid: int) -> None:
        p = self.pos.pop(rid, None)
        if p is None or not self.vivo[p]:
            return
        self.vivo[p] = False
        self.ids[p] = None
        self.metas[p] = None
        self.mortos += 1
        self.versao += 1

    def compactar_se_preciso(self) -> None:
        if self.mortos < 4096 or self.mortos * 4 < self.n:
            return
        manter = np.nonzero(self.vivo[:self.n])[0]
        k = len(manter)
        self.matriz[:k] = self.matriz[manter]
        self.rids[:k] = self.rids[manter]
        self.ids = [self.ids[i] for i in manter]
        self.metas = [self.metas[i] for i in manter]
        self.vivo[:] = False
        self.vivo[:k] = True
        self.n, self.mortos = k, 0
        self.pos = {int(self.rids[i]): i for i in range(k)}
        self.versao += 1


class ColecaoSqlite:
    """Uma colecao no estilo do ChromaDB, sobre um arquivo SQLite."""

    def __init__(self, cliente: "ClienteSqlite", nome: str, metadata: dict,
                 embedding_function: Any = None):
        self._cliente = cliente
        self.name = nome
        self.metadata = metadata
        self._embedding_function = embedding_function
        self._cache: _Cache | None = None
        self._mascaras: OrderedDict = OrderedDict()
        self._lock = threading.RLock()

    # -- cache -----------------------------------------------------------------

    def _dim(self, c: sqlite3.Connection) -> int | None:
        r = c.execute("SELECT dim FROM colecoes WHERE nome=?", (self.name,)).fetchone()
        return r[0] if r else None

    def _seq_atual(self, c: sqlite3.Connection) -> int:
        r = c.execute("SELECT seq FROM sqlite_sequence WHERE name='mudancas'").fetchone()
        return int(r[0]) if r else 0

    def _carregar(self, c: sqlite3.Connection, dim: int) -> None:
        cache = _Cache(dim)
        cache.seq = self._seq_atual(c)
        for rid, id_, meta, blob in c.execute(
                "SELECT rid, id, meta, vec FROM chunks WHERE col=? ORDER BY rid", (self.name,)):
            cache.por(rid, id_, json.loads(meta), blob)
        self._cache = cache
        self._mascaras.clear()

    def _sincronizar(self, c: sqlite3.Connection) -> _Cache | None:
        dim = self._dim(c)
        if dim is None:
            self._cache = None
            return None
        cache = self._cache
        if cache is None or cache.dim != dim:
            self._carregar(c, dim)
            return self._cache
        atual = self._seq_atual(c)
        if atual == cache.seq:
            return cache
        menor = c.execute("SELECT MIN(seq) FROM mudancas").fetchone()[0]
        if menor is None or menor > cache.seq + 1:
            # O registro foi podado alem do que este processo ja viu.
            self._carregar(c, dim)
            return self._cache
        pendentes = c.execute(
            "SELECT rid, op FROM mudancas WHERE col=? AND seq>? AND seq<=? ORDER BY seq",
            (self.name, cache.seq, atual)).fetchall()
        # So a ultima operacao de cada linha importa.
        final: dict[int, str] = {}
        for rid, op in pendentes:
            final[rid] = op
        for rid, op in final.items():
            if op == "d":
                cache.tirar(rid)
                continue
            r = c.execute("SELECT id, meta, vec FROM chunks WHERE rid=?", (rid,)).fetchone()
            if r is None:
                cache.tirar(rid)
            else:
                cache.por(rid, r[0], json.loads(r[1]), r[2])
        cache.seq = atual
        cache.compactar_se_preciso()
        self._mascaras.clear()
        return cache

    def _mascara(self, cache: _Cache, where: dict | None) -> np.ndarray:
        vivo = cache.vivo[:cache.n]
        if where is None:
            return vivo
        chave = (cache.versao, json.dumps(where, sort_keys=True, default=str))
        achada = self._mascaras.get(chave)
        if achada is not None:
            self._mascaras.move_to_end(chave)
            return achada
        pred = _predicado(where)
        metas = cache.metas
        m = np.fromiter((metas[i] is not None and pred(metas[i]) for i in range(cache.n)),
                        dtype=bool, count=cache.n)
        m &= vivo
        self._mascaras[chave] = m
        while len(self._mascaras) > 32:
            self._mascaras.popitem(last=False)
        return m

    def _mascara_documento(self, c, cache: _Cache, wd: dict) -> np.ndarray:
        """`where_document` do Chroma: $contains, $not_contains, $and, $or."""
        if not isinstance(wd, dict) or len(wd) != 1:
            raise IndiceSqliteErro(f"where_document precisa de um operador, veio {wd!r}")
        (op, valor), = wd.items()
        if op in ("$and", "$or"):
            if not isinstance(valor, list) or not valor:
                raise IndiceSqliteErro(f"{op} precisa de uma lista nao vazia")
            partes = [self._mascara_documento(c, cache, w) for w in valor]
            out = partes[0].copy()
            for q in partes[1:]:
                out = (out & q) if op == "$and" else (out | q)
            return out
        if op not in ("$contains", "$not_contains") or not isinstance(valor, str) or not valor:
            raise IndiceSqliteErro(f"where_document nao suportado: {wd!r}")
        if len(valor) >= 3 and c.tem_fts:
            # O trigram descarta quase tudo; o instr() confirma, porque o FTS5
            # ignora maiusculas e o Chroma nao.
            achados = c.execute(
                "SELECT k.rid FROM chunks_fts f JOIN chunks k ON k.rid=f.rowid "
                "WHERE chunks_fts MATCH ? AND k.col=? AND instr(k.doc, ?)>0",
                ('"' + valor.replace('"', '""') + '"', self.name, valor))
        else:
            achados = c.execute("SELECT rid FROM chunks WHERE col=? AND instr(doc, ?)>0",
                                (self.name, valor))
        m = np.zeros(cache.n, dtype=bool)
        for (rid,) in achados:
            p = cache.pos.get(rid)
            if p is not None:
                m[p] = True
        return m if op == "$contains" else ~m

    def _filtrar(self, c, cache: _Cache, where, where_document) -> np.ndarray:
        m = self._mascara(cache, where)
        if where_document is not None:
            m = m & self._mascara_documento(c, cache, where_document)
        return m

    # -- escrita ---------------------------------------------------------------

    def _embutir(self, documentos: list[str]) -> list[Any]:
        ef = self._embedding_function
        if ef is None:
            raise IndiceSqliteErro("sem embeddings e sem funcao de embedding na colecao")
        return list(ef(documentos))

    def _preparar(self, ids, embeddings, metadatas, documentos):
        n = len(ids)
        if len(set(ids)) != n:
            repetidos = sorted({i for i in ids if ids.count(i) > 1})
            raise IndiceSqliteErro(f"ids repetidos no mesmo lote: {repetidos[:3]}")
        for nome, seq in (("embeddings", embeddings), ("metadatas", metadatas),
                          ("documents", documentos)):
            if seq is not None and len(seq) != n:
                raise IndiceSqliteErro(f"{nome} tem {len(seq)} itens para {n} ids")
        return n

    def upsert(self, ids: list[str], embeddings: Any = None, metadatas: list[dict] | None = None,
               documents: list[str] | None = None) -> None:
        self._gravar(ids, embeddings, metadatas, documents, modo="upsert")

    def add(self, ids, embeddings=None, metadatas=None, documents=None) -> None:
        self._gravar(ids, embeddings, metadatas, documents, modo="add")

    def update(self, ids, embeddings=None, metadatas=None, documents=None) -> None:
        self._gravar(ids, embeddings, metadatas, documents, modo="update")

    def _gravar(self, ids, embeddings, metadatas, documentos, *, modo: str) -> None:
        ids = list(ids)
        if not ids:
            return
        self._preparar(ids, embeddings, metadatas, documentos)
        # O embedding e calculado FORA da transacao: pode levar segundos, e um
        # escritor parado dentro de BEGIN IMMEDIATE bloquearia todos os outros.
        if embeddings is None and documentos is not None:
            embeddings = self._embutir(list(documentos))
        vetores = None
        if embeddings is not None:
            vetores = [np.asarray(v, dtype=np.float32).ravel() for v in embeddings]
        with self._lock:
            c = self._cliente._conexao()
            c.execute("BEGIN IMMEDIATE")
            try:
                dim = self._dim(c)
                if dim is None:
                    raise IndiceSqliteErro(f"colecao {self.name} nao existe")
                if vetores is not None:
                    d = len(vetores[0])
                    if dim == 0:
                        c.execute("UPDATE colecoes SET dim=? WHERE nome=?", (d, self.name))
                        dim = d
                    for v in vetores:
                        if len(v) != dim:
                            raise IndiceSqliteErro(
                                f"Collection expecting embedding with dimension of {dim}, "
                                f"got {len(v)}")
                for i, id_ in enumerate(ids):
                    ex = c.execute("SELECT rid, doc, meta, vec FROM chunks WHERE col=? AND id=?",
                                   (self.name, id_)).fetchone()
                    novo_meta = dict(metadatas[i]) if metadatas is not None and metadatas[i] else {}
                    novo_doc = documentos[i] if documentos is not None else None
                    novo_vec = vetores[i] if vetores is not None else None
                    if ex is None:
                        if modo == "update":
                            continue
                        if novo_vec is None:
                            raise IndiceSqliteErro(f"{id_}: sem embedding para um id novo")
                        cur = c.execute(
                            "INSERT INTO chunks(col, id, doc, meta, vec) VALUES (?,?,?,?,?)",
                            (self.name, id_, novo_doc,
                             json.dumps(novo_meta, ensure_ascii=False), novo_vec.tobytes()))
                        c.execute("INSERT INTO mudancas(col, rid, op) VALUES (?,?,'u')",
                                  (self.name, cur.lastrowid))
                        continue
                    if modo == "add":
                        continue   # o Chroma ignora o id que ja existe
                    rid, doc, meta, vec = ex
                    mesclado = json.loads(meta)
                    mesclado.update(novo_meta)
                    c.execute("UPDATE chunks SET doc=?, meta=?, vec=? WHERE rid=?",
                              (novo_doc if novo_doc is not None else doc,
                               json.dumps(mesclado, ensure_ascii=False),
                               novo_vec.tobytes() if novo_vec is not None else vec, rid))
                    c.execute("INSERT INTO mudancas(col, rid, op) VALUES (?,?,'u')",
                              (self.name, rid))
                self._podar(c)
                c.execute("COMMIT")
            except BaseException:
                c.execute("ROLLBACK")
                raise

    def _podar(self, c: sqlite3.Connection) -> None:
        total = c.execute("SELECT COUNT(*) FROM mudancas").fetchone()[0]
        if total > MUDANCAS_MAXIMAS:
            corte = c.execute("SELECT seq FROM mudancas ORDER BY seq LIMIT 1 OFFSET ?",
                              (total - MUDANCAS_MAXIMAS // 2,)).fetchone()[0]
            c.execute("DELETE FROM mudancas WHERE seq<?", (corte,))

    def delete(self, ids: list[str] | None = None, where: dict | None = None,
               where_document: dict | None = None) -> None:
        if ids is None and where is None and where_document is None:
            raise IndiceSqliteErro("delete precisa de ids ou de where")
        with self._lock:
            c = self._cliente._conexao()
            c.execute("BEGIN IMMEDIATE")
            try:
                if self._dim(c) is None:
                    raise IndiceSqliteErro(f"colecao {self.name} nao existe")
                cache = self._sincronizar(c)
                alvo: set[int] = set()
                if cache is not None:
                    conjunto = set(ids) if ids is not None else None
                    m = self._filtrar(c, cache, where, where_document)
                    for p in np.nonzero(m)[0]:
                        if conjunto is None or cache.ids[p] in conjunto:
                            alvo.add(int(cache.rids[p]))
                for rid in alvo:
                    c.execute("DELETE FROM chunks WHERE rid=?", (rid,))
                    c.execute("INSERT INTO mudancas(col, rid, op) VALUES (?,?,'d')",
                              (self.name, rid))
                self._podar(c)
                c.execute("COMMIT")
            except BaseException:
                c.execute("ROLLBACK")
                raise

    # -- leitura ---------------------------------------------------------------

    def count(self) -> int:
        with self._lock:
            c = self._cliente._conexao()
            cache = self._sincronizar(c)
            return 0 if cache is None else int(cache.vivo[:cache.n].sum())

    def _linhas(self, c, rids: list[int], colunas: str) -> dict[int, tuple]:
        out: dict[int, tuple] = {}
        for i in range(0, len(rids), 500):
            lote = rids[i:i + 500]
            marcas = ",".join("?" * len(lote))
            for r in c.execute(f"SELECT rid, {colunas} FROM chunks WHERE rid IN ({marcas})", lote):
                out[r[0]] = r[1:]
        return out

    def get(self, ids: list[str] | None = None, where: dict | None = None,
            limit: int | None = None, offset: int | None = None,
            include: list[str] | None = None, **_ignorado) -> dict:
        where_document = _ignorado.get("where_document")
        include = ["metadatas", "documents"] if include is None else list(include)
        with self._lock:
            c = self._cliente._conexao()
            cache = self._sincronizar(c)
            vazio = {"ids": [], "embeddings": None, "documents": None, "uris": None,
                     "included": include, "data": None, "metadatas": None}
            if cache is None or cache.n == 0:
                if "metadatas" in include:
                    vazio["metadatas"] = []
                if "documents" in include:
                    vazio["documents"] = []
                if "embeddings" in include:
                    vazio["embeddings"] = np.zeros((0, 0), dtype=np.float32)
                return vazio
            m = self._filtrar(c, cache, where, where_document)
            if ids is not None:
                conjunto = set(ids)
                m = m & np.fromiter((i in conjunto for i in cache.ids[:cache.n]),
                                    dtype=bool, count=cache.n)
            pos = np.nonzero(m)[0]
            if offset:
                pos = pos[offset:]
            if limit is not None:
                pos = pos[:limit]
            rids = [int(cache.rids[p]) for p in pos]
            colunas = []
            if "documents" in include:
                colunas.append("doc")
            if "embeddings" in include:
                colunas.append("vec")
            extra = self._linhas(c, rids, ", ".join(colunas)) if colunas else {}
            out = {"ids": [cache.ids[p] for p in pos], "embeddings": None, "documents": None,
                   "uris": None, "included": include, "data": None, "metadatas": None}
            if "metadatas" in include:
                out["metadatas"] = [dict(cache.metas[p]) for p in pos]
            k = 0
            if "documents" in include:
                out["documents"] = [extra[r][k] for r in rids]
                k += 1
            if "embeddings" in include:
                col = k
                out["embeddings"] = (np.stack([np.frombuffer(extra[r][col], dtype=np.float32)
                                               for r in rids])
                                     if rids else np.zeros((0, cache.dim), dtype=np.float32))
            return out

    def buscar_texto(self, texto: str, n_results: int = 10, where: dict | None = None) -> dict:
        """Busca lexical (BM25 sobre trigramas) com o mesmo `where` da busca vetorial.

        O Chroma nao tem isto: o FTS5 dele so responde a `where_document`.
        Devolve ids, documentos, metadados e `scores` (maior e melhor).
        """
        vazio = {"ids": [], "documents": [], "metadatas": [], "scores": []}
        palavras = [w for w in texto.split() if len(w) >= 3]
        with self._lock:
            c = self._cliente._conexao()
            if not palavras or not c.tem_fts:
                return vazio
            cache = self._sincronizar(c)
            if cache is None or cache.n == 0:
                return vazio
            permitido = self._mascara(cache, where)
            consulta = " OR ".join('"' + w.replace('"', '""') + '"' for w in palavras)
            achados = []
            for rid, bm in c.execute(
                    "SELECT f.rowid, bm25(chunks_fts) FROM chunks_fts f "
                    "WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts) LIMIT ?",
                    (consulta, max(n_results * 20, 200))):
                p = cache.pos.get(rid)
                if p is not None and permitido[p]:
                    achados.append((rid, p, -bm))
                    if len(achados) == n_results:
                        break
            docs = self._linhas(c, [r for r, _, _ in achados], "doc") if achados else {}
            return {"ids": [cache.ids[p] for _, p, _ in achados],
                    "documents": [docs[r][0] for r, _, _ in achados],
                    "metadatas": [dict(cache.metas[p]) for _, p, _ in achados],
                    "scores": [s for _, _, s in achados]}

    def hibrida(self, texto: str, query_embeddings: Any = None, n_results: int = 10,
                where: dict | None = None, k: int = 60) -> dict:
        """Fusao por reciprocidade (RRF) entre a busca vetorial e a lexical."""
        vet = self.query(query_embeddings=query_embeddings,
                         query_texts=None if query_embeddings is not None else [texto],
                         n_results=n_results * 3, where=where)
        lex = self.buscar_texto(texto, n_results * 3, where)
        pontos: dict[str, float] = {}
        for lista in (vet["ids"][0], lex["ids"]):
            for r, id_ in enumerate(lista):
                pontos[id_] = pontos.get(id_, 0.0) + 1.0 / (k + r + 1)
        ordem = sorted(pontos, key=lambda i: -pontos[i])[:n_results]
        dados = self.get(ids=ordem)
        por_id = {i: (d, m) for i, d, m in zip(dados["ids"], dados["documents"], dados["metadatas"])}
        return {"ids": ordem, "documents": [por_id[i][0] for i in ordem],
                "metadatas": [por_id[i][1] for i in ordem], "scores": [pontos[i] for i in ordem]}

    def peek(self, limit: int = 10) -> dict:
        return self.get(limit=limit, include=["metadatas", "documents", "embeddings"])

    def query(self, query_embeddings: Any = None, query_texts: list[str] | None = None,
              n_results: int = 10, where: dict | None = None,
              include: list[str] | None = None, **_ignorado) -> dict:
        where_document = _ignorado.get("where_document")
        include = ["metadatas", "documents", "distances"] if include is None else list(include)
        if query_embeddings is None:
            if not query_texts:
                raise IndiceSqliteErro("query precisa de query_texts ou query_embeddings")
            query_embeddings = self._embutir(list(query_texts))
        consultas = [np.asarray(q, dtype=np.float32).ravel() for q in query_embeddings]
        resultado = {"ids": [], "embeddings": None, "documents": None, "uris": None,
                     "included": include, "data": None, "metadatas": None, "distances": None}
        if "documents" in include:
            resultado["documents"] = []
        if "metadatas" in include:
            resultado["metadatas"] = []
        if "distances" in include:
            resultado["distances"] = []
        with self._lock:
            c = self._cliente._conexao()
            cache = self._sincronizar(c)
            for q in consultas:
                if cache is None or cache.n == 0:
                    ordem, dist = np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.float32)
                else:
                    if len(q) != cache.dim:
                        raise IndiceSqliteErro(
                            f"Collection expecting embedding with dimension of {cache.dim}, "
                            f"got {len(q)}")
                    norma = float(np.linalg.norm(q))
                    qn = q / norma if norma > 0 else q
                    idx = np.nonzero(self._filtrar(c, cache, where, where_document))[0]
                    k = min(max(int(n_results), 0), len(idx))
                    if k == 0:
                        ordem, dist = np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.float32)
                    else:
                        sc = cache.matriz[idx] @ qn
                        top = np.argpartition(-sc, k - 1)[:k] if k < len(idx) else np.arange(len(idx))
                        top = top[np.argsort(-sc[top], kind="stable")]
                        ordem, dist = idx[top], 1.0 - sc[top]
                resultado["ids"].append([cache.ids[p] for p in ordem] if cache else [])
                if "metadatas" in include:
                    resultado["metadatas"].append([dict(cache.metas[p]) for p in ordem] if cache else [])
                if "distances" in include:
                    resultado["distances"].append([float(d) for d in dist])
                if "documents" in include:
                    rids = [int(cache.rids[p]) for p in ordem] if cache else []
                    docs = self._linhas(c, rids, "doc") if rids else {}
                    resultado["documents"].append([docs[r][0] for r in rids])
        return resultado

    # -- colecao ---------------------------------------------------------------

    def modify(self, name: str | None = None, metadata: dict | None = None) -> None:
        with self._lock:
            c = self._cliente._conexao()
            c.execute("BEGIN IMMEDIATE")
            try:
                if name and name != self.name:
                    if c.execute("SELECT 1 FROM colecoes WHERE nome=?", (name,)).fetchone():
                        raise IndiceSqliteErro(f"ja existe uma colecao chamada {name}")
                    c.execute("UPDATE colecoes SET nome=? WHERE nome=?", (name, self.name))
                    c.execute("UPDATE chunks SET col=? WHERE col=?", (name, self.name))
                    c.execute("UPDATE mudancas SET col=? WHERE col=?", (name, self.name))
                    self.name = name
                    self._cache = None
                if metadata is not None:
                    c.execute("UPDATE colecoes SET metadata=? WHERE nome=?",
                              (json.dumps(metadata), self.name))
                    self.metadata = metadata
                c.execute("COMMIT")
            except BaseException:
                c.execute("ROLLBACK")
                raise


class ClienteSqlite:
    """O que o resto do codigo espera de um `chromadb.PersistentClient`."""

    def __init__(self, pasta: str | os.PathLike):
        self.pasta = Path(pasta)
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.arquivo = self.pasta / NOME_DO_ARQUIVO
        self._local = threading.local()
        self._colecoes: dict[str, ColecaoSqlite] = {}
        self._lock = threading.Lock()
        self._conexao()

    def _conexao(self) -> sqlite3.Connection:
        c = getattr(self._local, "c", None)
        if c is None:
            c = self._local.c = _conectar(self.arquivo)
        return c

    def close(self) -> None:
        c = getattr(self._local, "c", None)
        if c is not None:
            c.close()
            self._local.c = None

    def _colecao(self, nome: str, ef: Any) -> ColecaoSqlite:
        with self._lock:
            col = self._colecoes.get(nome)
            if col is None:
                meta = json.loads(self._conexao().execute(
                    "SELECT metadata FROM colecoes WHERE nome=?", (nome,)).fetchone()[0])
                col = self._colecoes[nome] = ColecaoSqlite(self, nome, meta, ef)
            elif ef is not None:
                col._embedding_function = ef
            return col

    def list_collections(self) -> list[ColecaoSqlite]:
        nomes = [r[0] for r in self._conexao().execute("SELECT nome FROM colecoes ORDER BY nome")]
        return [self._colecao(n, None) for n in nomes]

    def get_collection(self, name: str, embedding_function: Any = None) -> ColecaoSqlite:
        if not self._conexao().execute("SELECT 1 FROM colecoes WHERE nome=?", (name,)).fetchone():
            raise IndiceSqliteErro(f"Collection {name} does not exist.")
        return self._colecao(name, embedding_function)

    def get_or_create_collection(self, name: str, embedding_function: Any = None,
                                 metadata: dict | None = None) -> ColecaoSqlite:
        metadata = dict(metadata or {})
        espaco = metadata.get("hnsw:space", "cosine")
        if espaco != "cosine":
            raise IndiceSqliteErro(f"so o espaco cosine e suportado, veio {espaco!r}")
        c = self._conexao()
        c.execute("INSERT OR IGNORE INTO colecoes(nome, metadata, dim) VALUES (?,?,0)",
                  (name, json.dumps(metadata)))
        return self._colecao(name, embedding_function)

    create_collection = get_or_create_collection

    def delete_collection(self, name: str) -> None:
        c = self._conexao()
        c.execute("BEGIN IMMEDIATE")
        try:
            c.execute("DELETE FROM chunks WHERE col=?", (name,))
            c.execute("DELETE FROM mudancas WHERE col=?", (name,))
            c.execute("DELETE FROM colecoes WHERE nome=?", (name,))
            c.execute("COMMIT")
        except BaseException:
            c.execute("ROLLBACK")
            raise
        with self._lock:
            self._colecoes.pop(name, None)

    def backup(self, destino: str | os.PathLike) -> Path:
        """Copia consistente com o banco em uso (API de backup do SQLite).

        Ao contrario de copiar a pasta do Chroma, que pode pegar o SQLite e os
        arquivos HNSW em momentos diferentes, isto e um instantaneo transacional.
        """
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        tmp = destino.with_suffix(destino.suffix + ".parcial")
        saida = sqlite3.connect(str(tmp))
        try:
            self._conexao().backup(saida)
        finally:
            saida.close()
        os.replace(tmp, destino)
        return destino

    def verificar(self) -> str:
        """`PRAGMA integrity_check`: 'ok' ou a descricao do dano."""
        return str(self._conexao().execute("PRAGMA integrity_check").fetchone()[0])
