"""Registro de recordacao: o que a busca devolveu, para qual pergunta, com que confianca.

## Por que existe

O delegation-core nao guardava o que o `search_vault` respondia. Sem isso nao
ha como saber quais notas de fato servem (voltam em muitas perguntas
diferentes), quais nunca voltam em pergunta nenhuma, e quais perguntas se
repetem sem resposta boa, que e onde falta conhecimento no vault.

O openclaw decide o que promover da memoria curta para a longa exatamente por
isso (`memory-host-sdk/dreaming.ts`): uma memoria so e promovida depois de
voltar em pelo menos 3 recordacoes, de 3 consultas diferentes, com meia-vida
de 14 dias. Este modulo e o registro que torna esse tipo de decisao possivel.

## O que guarda

Uma linha por (consulta, nota devolvida): quando, o hash da consulta, o texto
dela (cortado), a posicao da nota, e a confianca da busca. O texto da consulta
fica porque sem ele uma lacuna ("perguntaram 5 vezes e ninguem respondeu") nao
diz o que foi perguntado.

## Criterio de lego

sqlite3 e hashlib. Recebe consultas e caminhos, devolve contagens. Nao sabe o
que e vault, busca ou MCP.
"""

from __future__ import annotations

import hashlib
import math
import sqlite3
import threading
import time
from collections.abc import Iterable
from pathlib import Path

MAX_CONSULTA = 300


def _hash(consulta: str) -> str:
    norm = " ".join((consulta or "").lower().split())
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16]


class RegistroDeRecordacao:
    def __init__(self, caminho: str | Path):
        self.caminho = Path(caminho)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self._trava = threading.Lock()
        self._con = sqlite3.connect(str(self.caminho), check_same_thread=False)
        self._con.executescript(
            """
            PRAGMA journal_mode = WAL;
            CREATE TABLE IF NOT EXISTS consultas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                em REAL NOT NULL, hash TEXT NOT NULL, texto TEXT NOT NULL,
                confianca TEXT NOT NULL DEFAULT '', melhor REAL, n INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS devolvidas (
                consulta INTEGER NOT NULL, caminho TEXT NOT NULL, posicao INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS devolvidas_caminho ON devolvidas(caminho);
            CREATE INDEX IF NOT EXISTS consultas_em ON consultas(em);
            CREATE TABLE IF NOT EXISTS aberturas (
                em REAL NOT NULL, caminho TEXT NOT NULL, consulta INTEGER, posicao INTEGER
            );
            """
        )

    def fechar(self) -> None:
        with self._trava:
            self._con.close()

    def registrar(self, consulta: str, caminhos: Iterable[str], confianca: str = "",
                  melhor: float | None = None, em: float | None = None) -> int:
        caminhos = [c for c in caminhos if c]
        em = time.time() if em is None else em
        with self._trava, self._con:
            cur = self._con.execute(
                "INSERT INTO consultas(em, hash, texto, confianca, melhor, n) VALUES (?, ?, ?, ?, ?, ?)",
                (em, _hash(consulta), (consulta or "")[:MAX_CONSULTA], confianca or "", melhor, len(caminhos)),
            )
            cid = cur.lastrowid
            self._con.executemany("INSERT INTO devolvidas(consulta, caminho, posicao) VALUES (?, ?, ?)",
                                  [(cid, c, i + 1) for i, c in enumerate(caminhos)])
        return cid

    def mais_lembradas(self, desde: float = 0.0, min_consultas_unicas: int = 3, topo: int = 3,
                       meia_vida_dias: float = 14.0, agora: float | None = None, limite: int = 20) -> list[dict]:
        """Notas que voltaram entre as `topo` primeiras em varias consultas DIFERENTES.

        A pontuacao soma, por recordacao, 2^(-idade/meia_vida): uma nota que
        voltou muito ha dois meses pesa menos que uma que voltou esta semana.
        """
        agora = time.time() if agora is None else agora
        with self._trava:
            linhas = self._con.execute(
                "SELECT d.caminho, c.hash, c.em FROM devolvidas d JOIN consultas c ON c.id = d.consulta "
                "WHERE c.em >= ? AND d.posicao <= ?", (desde, topo)).fetchall()
        por: dict[str, dict] = {}
        for caminho, h, em in linhas:
            p = por.setdefault(caminho, {"caminho": caminho, "recordacoes": 0, "consultas_unicas": set(),
                                          "pontos": 0.0, "ultima": 0.0})
            p["recordacoes"] += 1
            p["consultas_unicas"].add(h)
            p["pontos"] += math.pow(2.0, -max(agora - em, 0) / 86400 / meia_vida_dias)
            p["ultima"] = max(p["ultima"], em)
        saida = []
        for p in por.values():
            if len(p["consultas_unicas"]) >= min_consultas_unicas:
                saida.append({**p, "consultas_unicas": len(p["consultas_unicas"]), "pontos": round(p["pontos"], 3)})
        saida.sort(key=lambda d: (-d["pontos"], d["caminho"]))
        return saida[:limite]

    def nunca_lembradas(self, existentes: Iterable[str], desde: float = 0.0) -> list[str]:
        """Das notas existentes, as que nao voltaram em consulta nenhuma desde `desde`."""
        with self._trava:
            vistas = {r[0] for r in self._con.execute(
                "SELECT DISTINCT d.caminho FROM devolvidas d JOIN consultas c ON c.id = d.consulta "
                "WHERE c.em >= ?", (desde,))}
        return sorted(set(existentes) - vistas)

    def lacunas(self, desde: float = 0.0, min_repeticoes: int = 2,
                confiancas_ruins: tuple[str, ...] = ("low", "none", "")) -> list[dict]:
        """Perguntas repetidas cuja melhor resposta nunca passou de confianca ruim.

        E onde falta conhecimento no vault: alguem precisou disso mais de uma
        vez e a busca nunca teve uma boa resposta.
        """
        with self._trava:
            linhas = self._con.execute(
                "SELECT hash, max(texto), count(*), group_concat(DISTINCT confianca), max(melhor), max(em) "
                "FROM consultas WHERE em >= ? GROUP BY hash HAVING count(*) >= ?",
                (desde, min_repeticoes)).fetchall()
        saida = []
        for h, texto, n, confs, melhor, ultima in linhas:
            conjunto = set((confs or "").split(",")) if confs is not None else {""}
            if conjunto <= set(confiancas_ruins):
                saida.append({"consulta": texto, "vezes": n, "melhor_similaridade": melhor, "ultima": ultima})
        saida.sort(key=lambda d: (-d["vezes"], -d["ultima"]))
        return saida

    def registrar_abertura(self, caminho: str, janela_s: float = 900.0, em: float | None = None) -> dict:
        """O agente abriu a nota inteira. Se uma busca dos ultimos `janela_s` a devolveu, liga as duas.

        E o voto implicito (item 8 do catalogo; o paperclip guarda voto
        explicito em `feedback_votes`): abrir um resultado diz que ele servia,
        e a posicao em que ele estava diz se o ranking o pos onde devia.
        """
        em = time.time() if em is None else em
        with self._trava, self._con:
            ln = self._con.execute(
                "SELECT c.id, d.posicao FROM consultas c JOIN devolvidas d ON d.consulta = c.id "
                "WHERE d.caminho = ? AND c.em BETWEEN ? AND ? ORDER BY c.em DESC LIMIT 1",
                (caminho, em - janela_s, em)).fetchone()
            cid, pos = (ln if ln else (None, None))
            self._con.execute("INSERT INTO aberturas(em, caminho, consulta, posicao) VALUES (?, ?, ?, ?)",
                              (em, caminho, cid, pos))
        return {"consulta": cid, "posicao": pos}

    def aberturas_por_posicao(self, desde: float = 0.0, ate_posicao: int = 10) -> list[dict]:
        """Por posicao: quantas vezes um resultado ali foi devolvido e quantas foi aberto."""
        with self._trava:
            dev = dict(self._con.execute(
                "SELECT d.posicao, count(*) FROM devolvidas d JOIN consultas c ON c.id = d.consulta "
                "WHERE c.em >= ? AND d.posicao <= ? GROUP BY d.posicao", (desde, ate_posicao)).fetchall())
            ab = dict(self._con.execute(
                "SELECT posicao, count(*) FROM aberturas WHERE em >= ? AND posicao IS NOT NULL "
                "AND posicao <= ? GROUP BY posicao", (desde, ate_posicao)).fetchall())
        return [{"posicao": p, "devolvidas": dev.get(p, 0), "abertas": ab.get(p, 0),
                 "taxa": round(ab.get(p, 0) / dev[p], 3) if dev.get(p) else None}
                for p in range(1, ate_posicao + 1) if dev.get(p) or ab.get(p)]

    def aberturas_sem_busca(self, desde: float = 0.0) -> int:
        """Notas abertas sem busca antes: o agente ja sabia o nome, ou a busca nao as trouxe."""
        with self._trava:
            return self._con.execute("SELECT count(*) FROM aberturas WHERE em >= ? AND consulta IS NULL",
                                     (desde,)).fetchone()[0]

    def estatisticas(self) -> dict:
        with self._trava:
            c, u, d = self._con.execute(
                "SELECT count(*), count(DISTINCT hash), (SELECT count(DISTINCT caminho) FROM devolvidas) "
                "FROM consultas").fetchone()
        return {"consultas": c, "consultas_unicas": u, "notas_ja_devolvidas": d}
