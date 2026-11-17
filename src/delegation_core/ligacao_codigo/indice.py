"""Nome -> nos de codigo, de varios grafos, em sqlite. Cada grafo e refeito so quando o arquivo dele muda."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from .citacoes import _ARQUIVO, Alvo, chave_da_citacao


def _chaves_do_no(no: dict) -> list[str]:
    """`extract_csharp()` -> extract_csharp; `.load()` -> load; `IndiceLexico` -> indicelexico.

    Rotulo que e nome de arquivo fica inteiro: somar `()` fazia `graph.json`
    virar a chave `json`.
    """
    rot = (no.get("label") or "").strip()
    if not rot:
        return []
    if rot.endswith("()") or _ARQUIVO.search(rot):
        k = chave_da_citacao(rot)
    else:
        k = chave_da_citacao(rot + "()")
    return [k] if len(k) >= 3 else []


class IndiceDeCodigo:
    def __init__(self, caminho: str | Path):
        self.caminho = Path(caminho)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self._trava = threading.Lock()
        self._con = sqlite3.connect(str(self.caminho), check_same_thread=False)
        self._con.executescript(
            """
            PRAGMA journal_mode = WAL;
            CREATE TABLE IF NOT EXISTS grafos (grafo TEXT PRIMARY KEY, assinatura TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS nos (
                grafo TEXT NOT NULL, chave TEXT NOT NULL, id TEXT NOT NULL,
                rotulo TEXT NOT NULL, arquivo TEXT NOT NULL, linha TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sumidos (
                grafo TEXT NOT NULL, chave TEXT NOT NULL, rotulo TEXT NOT NULL, arquivo TEXT NOT NULL,
                sumiu_em REAL NOT NULL, PRIMARY KEY (grafo, chave)
            );
            CREATE INDEX IF NOT EXISTS nos_chave ON nos(chave);
            CREATE INDEX IF NOT EXISTS nos_grafo_id ON nos(grafo, id);
            """
        )

    def fechar(self) -> None:
        with self._trava:
            self._con.close()

    def assinatura(self, grafo: str) -> str | None:
        with self._trava:
            r = self._con.execute("SELECT assinatura FROM grafos WHERE grafo = ?", (grafo,)).fetchone()
        return r[0] if r else None

    @staticmethod
    def _linhas(grafo: str, dados: dict) -> list[tuple]:
        """So no de codigo entra: racional e conceito nao sao citados por nome.

        Arquivo sem no proprio entra pelo nome (`busca_hibrida.py`), uma vez.
        """
        linhas, arquivos, com_no = [], set(), set()
        for no in dados.get("nodes") or []:
            if no.get("file_type") != "code":
                continue
            arq = no.get("source_file") or ""
            loc = str(no.get("source_location") or "")
            for k in _chaves_do_no(no):
                linhas.append((grafo, k, str(no.get("id", "")), str(no.get("label", "")), arq, loc))
                if arq and k == arq.rsplit("/", 1)[-1].lower():
                    com_no.add(arq)  # o grafo ja tem um no para o arquivo
            if arq:
                arquivos.add(arq)
        # arquivo sem no proprio (o extrator de algumas linguagens so cria as
        # funcoes) entra pelo nome; com no proprio, entraria duas vezes
        for arq in sorted(arquivos - com_no):
            nome = arq.rsplit("/", 1)[-1]
            linhas.append((grafo, nome.lower(), "file:" + arq, nome, arq, ""))
        return linhas

    def carregar_grafo(self, grafo: str, dados: dict, assinatura: str, anterior: dict | None = None) -> int:
        """Troca os nos de `grafo` e anota os nomes que sumiram desde a carga anterior.

        Na primeira carga nao ha carga anterior; se o build deixou o grafo de
        antes (`anterior`, o `graph.anterior.json`), a diferenca vem dele.
        Nome que volta sai de `sumidos`.
        """
        import time

        linhas = self._linhas(grafo, dados)
        novas = {l[1] for l in linhas}
        with self._trava:
            velhas = {r[0]: (r[1], r[2]) for r in self._con.execute(
                "SELECT chave, rotulo, arquivo FROM nos WHERE grafo = ?", (grafo,))}
        if not velhas and anterior:
            velhas = {l[1]: (l[3], l[4]) for l in self._linhas(grafo, anterior)}
        agora = time.time()
        sumiram = [(grafo, k, r, a, agora) for k, (r, a) in velhas.items() if k not in novas]
        with self._trava, self._con:
            self._con.executemany("INSERT OR IGNORE INTO sumidos VALUES (?, ?, ?, ?, ?)", sumiram)
            self._con.executemany("DELETE FROM sumidos WHERE grafo = ? AND chave = ?", [(grafo, k) for k in novas])
            self._con.execute("DELETE FROM nos WHERE grafo = ?", (grafo,))
            self._con.executemany("INSERT INTO nos VALUES (?, ?, ?, ?, ?, ?)", linhas)
            self._con.execute("INSERT INTO grafos VALUES (?, ?) ON CONFLICT(grafo) DO UPDATE SET "
                              "assinatura = excluded.assinatura", (grafo, assinatura))
        return len(linhas)

    def esquecer_exceto(self, grafos: set[str]) -> list[str]:
        with self._trava, self._con:
            todos = [r[0] for r in self._con.execute("SELECT grafo FROM grafos")]
            saem = [g for g in todos if g not in grafos]
            for g in saem:
                self._con.execute("DELETE FROM nos WHERE grafo = ?", (g,))
                self._con.execute("DELETE FROM sumidos WHERE grafo = ?", (g,))
                self._con.execute("DELETE FROM grafos WHERE grafo = ?", (g,))
        return saem

    def sincronizar(self, grafos: dict[str, Path]) -> dict:
        """Recarrega o grafo cujo arquivo mudou (mtime e tamanho) e tira o que sumiu."""
        recarregados = []
        for nome, caminho in sorted(grafos.items()):
            try:
                st = Path(caminho).stat()
            except OSError:
                continue
            ass = f"{st.st_mtime_ns}:{st.st_size}"
            if self.assinatura(nome) == ass:
                continue
            try:
                dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            anterior = None
            ant = Path(caminho).with_name("graph.anterior.json")
            if self.assinatura(nome) is None and ant.is_file():
                try:
                    anterior = json.loads(ant.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    anterior = None
            self.carregar_grafo(nome, dados, ass, anterior)
            recarregados.append(nome)
        return {"reloaded": recarregados, "forgotten": self.esquecer_exceto(set(grafos))}

    def buscar(self, chave: str) -> list[Alvo]:
        with self._trava:
            linhas = self._con.execute("SELECT grafo, id, rotulo, arquivo, linha FROM nos WHERE chave = ? LIMIT 200",
                                       (chave.lower(),)).fetchall()
        return [Alvo(*r) for r in linhas]

    def sumido(self, chave: str) -> list[dict]:
        """Onde um nome existia e deixou de existir: [{graph, label, file, gone_at}]."""
        with self._trava:
            linhas = self._con.execute("SELECT grafo, rotulo, arquivo, sumiu_em FROM sumidos WHERE chave = ?",
                                       (chave.lower(),)).fetchall()
        return [{"graph": g, "label": r, "file": a, "gone_at": t} for g, r, a, t in linhas]

    def grafos(self) -> list[str]:
        with self._trava:
            return [r[0] for r in self._con.execute("SELECT grafo FROM grafos ORDER BY grafo")]
