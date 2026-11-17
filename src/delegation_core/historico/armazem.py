"""Historico das notas: toda versao guardada por conteudo, com diff e restauracao.

## Por que existe

Nada no delegation-core guardava a versao anterior de uma nota. E ele reescreve
notas em lote: `relink_folder` injeta `## Related`, a manutencao funde e
reclassifica, o `rename` repoe wikilinks em todas as notas que apontavam para a
renomeada. So na tarde de 26/09 quatro passes tocaram 528 notas (130 + 101 +
124 + 173, pela contagem do hook de inicio de sessao). Se um desses passes
estragar uma nota, nao ha volta: o vault nao e repositorio git, e o indice
guarda embedding, nao texto.

O desenho veio de duas bases: o grafana guarda cada versao de dashboard e
compara duas quaisquer (`pkg/components/dashdiffs`), e o openclaw fotografa
estado em sqlite antes de mexer (`src/snapshot/`, `infra/sqlite-snapshot.ts`).

## Como

- **Por conteudo**: cada versao e um blob zlib nomeado pelo sha256. Duas notas
  identicas, ou a mesma nota voltando a um texto antigo, custam um blob so.
- **Varredura, nao gancho**: `varrer()` compara mtime e tamanho com o que ja
  viu e so le o que mudou. Pega escrita de qualquer origem (o proprio
  delegation-core, o Obsidian, a pessoa num editor) sem depender de cada
  caminho de escrita lembrar de chamar alguma coisa. Quem vai reescrever em
  lote chama `varrer()` antes, e o estado anterior ao passe fica guardado.
- **Custo medido**: o vault desta maquina tem 10.567 notas, 31,2 MB em texto e
  10,0 MB em zlib; a leitura completa leva 0,4 s.

## Criterio de lego

Recebe uma raiz de armazenamento e caminhos relativos com conteudo. Nao sabe o
que e vault, config, indice ou MCP. So usa a biblioteca padrao.
"""

from __future__ import annotations

import difflib
import hashlib
import os
import sqlite3
import threading
import time
import zlib
from collections.abc import Iterable
from pathlib import Path


def _sha(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


def _linhas(texto: str) -> list[str]:
    """Linhas com quebra, inclusive a ultima.

    Texto sem quebra no fim deixava a ultima linha removida colada na primeira
    adicionada ("...e acabou+texto novo"), porque o difflib so emite a quebra
    que a linha ja tem. Visto no painel, na captura do historico de 27/09.
    """
    ls = texto.splitlines(keepends=True)
    if ls and not ls[-1].endswith(("\n", "\r")):
        ls[-1] += "\n"
    return ls


class Historico:
    def __init__(self, raiz: str | Path):
        self.raiz = Path(raiz)
        (self.raiz / "objetos").mkdir(parents=True, exist_ok=True)
        self._trava = threading.Lock()
        self._con = sqlite3.connect(str(self.raiz / "versoes.sqlite3"), check_same_thread=False)
        self._con.executescript(
            """
            PRAGMA journal_mode = WAL;
            CREATE TABLE IF NOT EXISTS versoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                caminho TEXT NOT NULL,
                sha TEXT NOT NULL,
                tamanho INTEGER NOT NULL,
                registrado_em REAL NOT NULL,
                origem TEXT NOT NULL DEFAULT '',
                nota TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS versoes_caminho ON versoes(caminho, id);
            CREATE TABLE IF NOT EXISTS vistos (
                caminho TEXT PRIMARY KEY, mtime_ns INTEGER NOT NULL, tamanho INTEGER NOT NULL
            );
            """
        )

    def fechar(self) -> None:
        with self._trava:
            self._con.close()

    # ── blobs ──────────────────────────────────────────────────────────────

    def _blob(self, sha: str) -> Path:
        return self.raiz / "objetos" / sha[:2] / sha[2:]

    def _guardar_blob(self, sha: str, conteudo: bytes) -> None:
        p = self._blob(sha)
        # Otimizacao, e nao correcao: regravar um blob de mesmo sha grava o mesmo
        # conteudo. A mutacao que tira esta linha sobrevive a suite, e e por isso.
        if p.exists():
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + f".{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_bytes(zlib.compress(conteudo, 6))
        os.replace(tmp, p)

    def conteudo(self, sha: str) -> bytes:
        return zlib.decompress(self._blob(sha).read_bytes())

    # ── registrar ──────────────────────────────────────────────────────────

    def registrar(self, caminho: str, conteudo: bytes | str, origem: str = "",
                  nota: str = "") -> dict | None:
        """Guarda uma versao. Devolve a linha nova, ou None se o texto e igual ao da ultima.

        Nao repetir a ultima e o que deixa a varredura ser chamada a vontade:
        chamar duas vezes sem mudanca no disco nao cria versao nenhuma.
        """
        if isinstance(conteudo, str):
            conteudo = conteudo.encode("utf-8")
        sha = _sha(conteudo)
        with self._trava:
            ultima = self._con.execute(
                "SELECT sha FROM versoes WHERE caminho = ? ORDER BY id DESC LIMIT 1", (caminho,)
            ).fetchone()
            if ultima and ultima[0] == sha:
                return None
            self._guardar_blob(sha, conteudo)
            agora = time.time()
            with self._con:
                cur = self._con.execute(
                    "INSERT INTO versoes(caminho, sha, tamanho, registrado_em, origem, nota) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (caminho, sha, len(conteudo), agora, origem, nota),
                )
            return {"id": cur.lastrowid, "caminho": caminho, "sha": sha, "tamanho": len(conteudo),
                    "registrado_em": agora, "origem": origem, "nota": nota}

    def varrer(self, raiz_vault: str | Path, arquivos: Iterable[str], origem: str = "varredura") -> dict:
        """Fotografa o que mudou desde a ultima varredura. `arquivos` sao caminhos relativos.

        Compara mtime em nanossegundos e tamanho com o que ja viu; so le o que
        difere. Arquivo que sumiu do disco nao e apagado do historico: o
        historico de uma nota apagada e justamente o que alguem vai querer.
        """
        raiz_vault = Path(raiz_vault)
        with self._trava:
            vistos = {c: (m, t) for c, m, t in self._con.execute("SELECT caminho, mtime_ns, tamanho FROM vistos")}
        novas = alteradas = lidas = 0
        atualizar: list[tuple[str, int, int]] = []
        for rel in arquivos:
            try:
                st = (raiz_vault / rel).stat()
            except OSError:
                continue
            marca = (st.st_mtime_ns, st.st_size)
            if vistos.get(rel) == marca:
                continue
            try:
                dados = (raiz_vault / rel).read_bytes()
            except OSError:
                continue
            lidas += 1
            r = self.registrar(rel, dados, origem=origem)
            if r is not None:
                if rel in vistos:
                    alteradas += 1
                else:
                    novas += 1
            atualizar.append((rel, *marca))
        if atualizar:
            with self._trava, self._con:
                self._con.executemany(
                    "INSERT INTO vistos(caminho, mtime_ns, tamanho) VALUES (?, ?, ?) "
                    "ON CONFLICT(caminho) DO UPDATE SET mtime_ns = excluded.mtime_ns, tamanho = excluded.tamanho",
                    atualizar,
                )
        return {"lidas": lidas, "novas": novas, "alteradas": alteradas}

    def renomear(self, de: str, para: str) -> int:
        """O historico acompanha a nota renomeada. Devolve quantas versoes mudaram de caminho."""
        with self._trava, self._con:
            n = self._con.execute("UPDATE versoes SET caminho = ? WHERE caminho = ?", (para, de)).rowcount
            self._con.execute("DELETE FROM vistos WHERE caminho = ?", (de,))
        return n

    # ── ler ────────────────────────────────────────────────────────────────

    def versoes(self, caminho: str, limite: int = 50) -> list[dict]:
        """Da mais nova para a mais antiga. `n` e a posicao: 1 e a atual."""
        with self._trava:
            linhas = self._con.execute(
                "SELECT id, sha, tamanho, registrado_em, origem, nota FROM versoes "
                "WHERE caminho = ? ORDER BY id DESC LIMIT ?", (caminho, int(limite)),
            ).fetchall()
        return [{"n": i + 1, "id": r[0], "sha": r[1], "tamanho": r[2], "registrado_em": r[3],
                 "origem": r[4], "nota": r[5]} for i, r in enumerate(linhas)]

    def caminhos(self, prefixo: str = "") -> list[str]:
        with self._trava:
            return [r[0] for r in self._con.execute(
                "SELECT DISTINCT caminho FROM versoes WHERE caminho LIKE ? ORDER BY caminho",
                (prefixo.replace("%", r"\%") + "%",))]

    def _por_n(self, caminho: str, n: int) -> dict | None:
        vs = self.versoes(caminho, limite=max(n, 1))
        return vs[n - 1] if 0 < n <= len(vs) else None

    def texto(self, caminho: str, n: int = 1) -> str | None:
        v = self._por_n(caminho, n)
        return None if v is None else self.conteudo(v["sha"]).decode("utf-8", errors="replace")

    def diff(self, caminho: str, de: int = 2, para: int = 1, contexto: int = 3) -> dict:
        """Diff unificado entre duas versoes, pela posicao (1 = a mais nova)."""
        va, vb = self._por_n(caminho, de), self._por_n(caminho, para)
        if va is None or vb is None:
            return {"ok": False, "motivo": "versao inexistente",
                    "versoes": len(self.versoes(caminho, limite=10_000))}
        a = _linhas(self.conteudo(va["sha"]).decode("utf-8", errors="replace"))
        b = _linhas(self.conteudo(vb["sha"]).decode("utf-8", errors="replace"))
        linhas = list(difflib.unified_diff(a, b, fromfile=f"{caminho} (v{de})",
                                           tofile=f"{caminho} (v{para})", n=contexto))
        mais = sum(1 for x in linhas if x.startswith("+") and not x.startswith("+++"))
        menos = sum(1 for x in linhas if x.startswith("-") and not x.startswith("---"))
        return {"ok": True, "de": va, "para": vb, "linhas_mais": mais, "linhas_menos": menos,
                "diff": "".join(linhas)}

    def mudancas_desde(self, desde: float, limite: int = 200) -> list[dict]:
        """O que ganhou versao depois de `desde` (epoch), agrupado por nota."""
        with self._trava:
            linhas = self._con.execute(
                "SELECT v.caminho, count(*), max(v.registrado_em), group_concat(DISTINCT v.origem), "
                "(SELECT min(registrado_em) FROM versoes w WHERE w.caminho = v.caminho) "
                "FROM versoes v WHERE v.registrado_em >= ? GROUP BY v.caminho "
                "ORDER BY max(v.registrado_em) DESC LIMIT ?", (float(desde), int(limite)),
            ).fetchall()
        # `primeira`: quando a nota entrou no historico. Uma nota cuja PRIMEIRA
        # versao cai na janela e que so tem essa versao foi fotografada pela
        # primeira vez, e nao mudou: na primeira varredura de um vault, sao todas.
        return [{"caminho": c, "versoes": n, "ultima": u, "origens": (o or "").split(","), "primeira": p}
                for c, n, u, o, p in linhas]

    # ── manutencao ─────────────────────────────────────────────────────────

    def podar(self, manter_por_nota: int = 50) -> dict:
        """Guarda as `manter_por_nota` versoes mais novas de cada nota e apaga blob orfao."""
        with self._trava, self._con:
            apagadas = self._con.execute(
                "DELETE FROM versoes WHERE id IN (SELECT id FROM ("
                " SELECT id, row_number() OVER (PARTITION BY caminho ORDER BY id DESC) AS r"
                " FROM versoes) WHERE r > ?)", (int(manter_por_nota),),
            ).rowcount
            vivos = {r[0] for r in self._con.execute("SELECT DISTINCT sha FROM versoes")}
        blobs = 0
        for sub in (self.raiz / "objetos").iterdir():
            if not sub.is_dir():
                continue
            for arq in sub.iterdir():
                if sub.name + arq.name not in vivos and not arq.name.endswith(".tmp"):
                    arq.unlink(missing_ok=True)
                    blobs += 1
        return {"versoes_apagadas": apagadas, "blobs_apagados": blobs}

    def estatisticas(self) -> dict:
        with self._trava:
            n, notas, cru = self._con.execute(
                "SELECT count(*), count(DISTINCT caminho), coalesce(sum(tamanho),0) FROM versoes").fetchone()
        disco = sum(f.stat().st_size for f in (self.raiz / "objetos").rglob("*") if f.is_file())
        return {"versoes": n, "notas": notas, "bytes_versionados": cru, "bytes_em_disco": disco}
