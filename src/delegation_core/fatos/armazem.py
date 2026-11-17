"""Fatos por nota, em sqlite: substitui por nota, responde por sujeito, aponta divergencia.

Cada nota e dona dos seus fatos: extrair de novo a mesma nota troca todos
eles, e nota apagada leva os seus junto (`esquecer_exceto`). A data do fato e
a data da nota, nao a da extracao: o valor "atual" e o da nota mais nova.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

import re

from .extracao import Fato, chave, normalizar, unico


def _casa(v: str) -> str:
    """`~`, `$HOME` e a casa real sao o mesmo lugar escrito de tres jeitos."""
    import os

    casa = os.path.expanduser("~").lower()
    return v.replace("$home", "~").replace("${home}", "~").replace(casa, "~")


def _compat(a: str, b: str) -> bool:
    a, b = _casa(a), _casa(b)
    return a in b or b in a


def _conflito(valores: list[dict]) -> tuple[dict, dict] | None:
    """O primeiro par (mais novo primeiro) de notas diferentes com valores incompativeis."""
    for i, x in enumerate(valores):
        for y in valores[i + 1:]:
            if x["note"] != y["note"] and not _compat(x["_kv"], y["_kv"]):
                return x, y
    return None


def re_pedacos(k: str) -> list[str]:
    return re.split(r"[_.:]+", k)


class ArmazemDeFatos:
    def __init__(self, caminho: str | Path):
        self.caminho = Path(caminho)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self._trava = threading.Lock()
        self._con = sqlite3.connect(str(self.caminho), check_same_thread=False)
        self._con.executescript(
            """
            PRAGMA journal_mode = WAL;
            CREATE TABLE IF NOT EXISTS notas (
                nota TEXT PRIMARY KEY, assinatura TEXT NOT NULL, data TEXT NOT NULL,
                extraido_em REAL NOT NULL, n INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS fatos (
                nota TEXT NOT NULL, data TEXT NOT NULL, sujeito TEXT NOT NULL, atributo TEXT NOT NULL,
                valor TEXT NOT NULL, citacao TEXT NOT NULL DEFAULT '',
                ks TEXT NOT NULL, ka TEXT NOT NULL, kv TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS fatos_chave ON fatos(ks, ka);
            CREATE INDEX IF NOT EXISTS fatos_nota ON fatos(nota);
            """
        )

    def fechar(self) -> None:
        with self._trava:
            self._con.close()

    def precisa(self, nota: str, assinatura: str) -> bool:
        with self._trava:
            r = self._con.execute("SELECT assinatura FROM notas WHERE nota = ?", (nota,)).fetchone()
        return r is None or r[0] != assinatura

    def substituir(self, nota: str, data: str, assinatura: str, fatos: list[Fato]) -> None:
        with self._trava, self._con:
            self._con.execute("DELETE FROM fatos WHERE nota = ?", (nota,))
            self._con.executemany(
                "INSERT INTO fatos(nota, data, sujeito, atributo, valor, citacao, ks, ka, kv) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(nota, data, f.sujeito, f.atributo, f.valor, f.citacao, chave(f.sujeito), chave(f.atributo),
                  normalizar(f.valor)) for f in fatos])
            self._con.execute(
                "INSERT INTO notas(nota, assinatura, data, extraido_em, n) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(nota) DO UPDATE SET assinatura = excluded.assinatura, data = excluded.data, "
                "extraido_em = excluded.extraido_em, n = excluded.n",
                (nota, assinatura, data, time.time(), len(fatos)))

    def esquecer_exceto(self, notas_vivas: set[str]) -> int:
        """Tira fatos de nota que nao existe mais. Devolve quantas notas sairam."""
        with self._trava, self._con:
            todas = [r[0] for r in self._con.execute("SELECT nota FROM notas")]
            mortas = [n for n in todas if n not in notas_vivas]
            for n in mortas:
                self._con.execute("DELETE FROM fatos WHERE nota = ?", (n,))
                self._con.execute("DELETE FROM notas WHERE nota = ?", (n,))
        return len(mortas)

    def _grupos(self, linhas) -> list[dict]:
        grupos: dict[tuple, dict] = {}
        for nota, data, s, a, v, cit, ks, ka, kv in linhas:
            g = grupos.setdefault((ks, ka), {"subject": s, "attribute": a, "values": []})
            g["values"].append({"value": v, "note": nota, "date": data, "quote": cit, "_kv": kv})
        saida = []
        for g in grupos.values():
            g["values"].sort(key=lambda x: (x["date"], x["note"]), reverse=True)
            g["current"] = g["values"][0]["value"]
            g["current_from"] = g["values"][0]["note"]
            # so atributo de valor unico diverge, so entre notas diferentes, e
            # so valor que nao contem o outro: `:11434` e `11434`, `localhost`
            # e `localhost:11434` sao o mesmo dito de dois jeitos
            par = _conflito(g["values"]) if unico(g["attribute"]) else None
            g["divergent"] = par is not None
            if par:
                g["conflict"] = [{"value": v["value"], "note": v["note"], "date": v["date"]} for v in par]
            for x in g["values"]:
                x.pop("_kv")
            saida.append(g)
        return saida

    def buscar(self, termo: str = "", sujeito: str = "", atributo: str = "", limite: int = 20,
               ate: str = "") -> list[dict]:
        """Grupos (sujeito, atributo) com o valor mais novo em `current` e o historico em `values`.

        `termo` casa por palavra em sujeito, atributo ou valor (todas as palavras
        tem que aparecer); `sujeito` e `atributo` casam pela chave, por prefixo.
        `ate` (AAAA-MM-DD) responde como o vault respondia naquele dia: so
        valores de notas com data ate ela, e `current` e o mais novo entre eles.
        """
        cond, args = [], []
        for p in normalizar(termo).split():
            cond.append("(ks LIKE ? OR ka LIKE ? OR kv LIKE ?)")
            args += [f"%{chave(p)}%", f"%{chave(p)}%", f"%{p}%"]
        if sujeito:
            cond.append("ks LIKE ?")
            args.append(chave(sujeito) + "%")
        if atributo:
            cond.append("ka LIKE ?")
            args.append(chave(atributo) + "%")
        sql = "SELECT nota, data, sujeito, atributo, valor, citacao, ks, ka, kv FROM fatos"
        if cond:
            # casa a chave inteira do grupo, para o historico vir completo
            sql += (" WHERE (ks, ka) IN (SELECT ks, ka FROM fatos WHERE " + " AND ".join(cond) + ")")
        if ate:
            sql += (" AND " if cond else " WHERE ") + "data <= ?"
            args.append(ate)
        with self._trava:
            linhas = self._con.execute(sql, args).fetchall()
        grupos = self._grupos(linhas)
        grupos.sort(key=lambda g: (-len(g["values"]), g["subject"].lower(), g["attribute"]))
        return grupos[:limite]

    def por_termos(self, termos: list[str], limite: int = 3) -> list[dict]:
        """Grupos cujo sujeito E atributo casam com termos da pergunta, o de mais termos primeiro.

        Para a busca: "qual a porta do llama" traz `llama.cpp / port`. Casa por
        pedaco da chave (`llama.cpp` -> `llama`, `cpp`) e por prefixo de 4
        letras, que junta "porta" com `port` e "modelo" com `model` sem
        dicionario. Exigir sujeito e atributo e o que segura o ruido: so o
        sujeito traria todos os fatos do delegation-core para qualquer pergunta.
        """
        tn = []
        for t in termos:
            t = chave(t)
            # palavra vazia ja saiu em termos_da_consulta; "go" e sujeito legitimo
            if t and t not in tn:
                tn.append(t)
        if not tn:
            return []

        def casa(t: str, pedacos: list[str]) -> bool:
            return any(p == t or (len(t) >= 4 and len(p) >= 4 and p[:4] == t[:4]) for p in pedacos)

        with self._trava:
            chaves = self._con.execute("SELECT DISTINCT ks, ka FROM fatos").fetchall()
        pontos = []
        for ks, ka in chaves:
            ps = [p for p in re_pedacos(ks) if p]
            pa = [p for p in re_pedacos(ka.removeprefix("setting:")) if p]
            ts = {t for t in tn if casa(t, ps)}
            ta = {t for t in tn if casa(t, pa)} - ts
            if ts and ta:
                pontos.append((len(ts) + len(ta), ks, ka))
        if not pontos:
            return []
        pontos.sort(key=lambda x: (-x[0], x[1], x[2]))
        escolhidas = [(ks, ka) for _, ks, ka in pontos[:limite]]
        with self._trava:
            linhas = []
            for ks, ka in escolhidas:
                linhas += self._con.execute(
                    "SELECT nota, data, sujeito, atributo, valor, citacao, ks, ka, kv FROM fatos "
                    "WHERE ks = ? AND ka = ?", (ks, ka)).fetchall()
        ordem = {k: i for i, k in enumerate(escolhidas)}
        grupos = self._grupos(linhas)
        grupos.sort(key=lambda g: ordem.get((chave(g["subject"]), chave(g["attribute"])), 99))
        return grupos

    def divergencias(self, limite: int = 20) -> list[dict]:
        """Onde notas diferentes dao valores diferentes para o mesmo sujeito e atributo."""
        with self._trava:
            chaves = self._con.execute(
                "SELECT ks, ka FROM fatos GROUP BY ks, ka "
                "HAVING COUNT(DISTINCT kv) > 1 AND COUNT(DISTINCT nota) > 1").fetchall()
            linhas = []
            for ks, ka in chaves:
                linhas += self._con.execute(
                    "SELECT nota, data, sujeito, atributo, valor, citacao, ks, ka, kv FROM fatos "
                    "WHERE ks = ? AND ka = ?", (ks, ka)).fetchall()
        grupos = [g for g in self._grupos(linhas) if g["divergent"]]
        grupos.sort(key=lambda g: g["values"][0]["date"], reverse=True)
        return grupos[:limite]

    def estatisticas(self) -> dict:
        with self._trava:
            n_notas, n_fatos = self._con.execute("SELECT COUNT(*), COALESCE(SUM(n), 0) FROM notas").fetchone()
            grupos = self._con.execute("SELECT COUNT(*) FROM (SELECT 1 FROM fatos GROUP BY ks, ka)").fetchone()[0]
        return {"notes": n_notas, "facts": n_fatos, "subjects_attributes": grupos}
