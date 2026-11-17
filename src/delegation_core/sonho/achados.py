"""Registro dos achados do sonho: nota nova que atualiza ou contradiz nota antiga.

## Por que existe

O sonho acha, por exemplo, que o drop-in de 26/09 revoga a decisao de 02/09.
Isso ia para uma nota de relatorio e parava ali: a nota de 02/09 continuava
voltando da busca como se valesse. E a falha que a memoria deste vault nomeia
("nao declare estado fechado"): estado antigo tratado como atual.

Guardar o achado permite que a busca diga, junto do resultado antigo, que ele
foi atualizado e por qual nota, citando as duas. Nenhuma nota e editada: o
aviso vive fora dela, e some se o achado for descartado.

## Criterio de lego

sqlite3. Recebe achados e caminhos; nao sabe o que e busca ou sonho.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path


class RegistroDeAchados:
    def __init__(self, caminho: str | Path):
        self.caminho = Path(caminho)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self._trava = threading.Lock()
        self._con = sqlite3.connect(str(self.caminho), check_same_thread=False)
        self._con.executescript(
            """
            PRAGMA journal_mode = WAL;
            CREATE TABLE IF NOT EXISTS achados (
                velha TEXT NOT NULL, nova TEXT NOT NULL, relacao TEXT NOT NULL,
                citacao_velha TEXT NOT NULL DEFAULT '', citacao_nova TEXT NOT NULL DEFAULT '',
                em REAL NOT NULL, descartado INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (velha, nova)
            );
            CREATE INDEX IF NOT EXISTS achados_velha ON achados(velha);
            """
        )

    def fechar(self) -> None:
        with self._trava:
            self._con.close()

    def registrar(self, velha: str, nova: str, relacao: str, citacao_velha: str = "",
                  citacao_nova: str = "", em: float | None = None) -> None:
        """Um par so tem um achado: o mais recente substitui, e um descarte anterior e mantido."""
        with self._trava, self._con:
            self._con.execute(
                "INSERT INTO achados(velha, nova, relacao, citacao_velha, citacao_nova, em) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(velha, nova) DO UPDATE SET "
                "relacao = excluded.relacao, citacao_velha = excluded.citacao_velha, "
                "citacao_nova = excluded.citacao_nova, em = excluded.em",
                (velha, nova, relacao, citacao_velha, citacao_nova, time.time() if em is None else em))

    def descartar(self, velha: str, nova: str) -> bool:
        """Alguem conferiu e o achado nao vale: some da busca e nao volta no proximo sonho."""
        with self._trava, self._con:
            return self._con.execute("UPDATE achados SET descartado = 1 WHERE velha = ? AND nova = ?",
                                     (velha, nova)).rowcount > 0

    def sobre(self, caminhos: list[str]) -> dict[str, list[dict]]:
        """Para cada caminho que alguma nota nova atualiza, os achados validos, mais novo primeiro."""
        if not caminhos:
            return {}
        with self._trava:
            linhas = self._con.execute(
                f"SELECT velha, nova, relacao, citacao_velha, citacao_nova, em FROM achados "
                f"WHERE descartado = 0 AND velha IN ({','.join('?' * len(caminhos))}) ORDER BY em DESC",
                list(caminhos)).fetchall()
        saida: dict[str, list[dict]] = {}
        for velha, nova, rel, cv, cn, em in linhas:
            saida.setdefault(velha, []).append({"by": nova, "relation": rel, "old_said": cv, "new_says": cn,
                                                "found_at": em})
        return saida

    def todos(self, incluir_descartados: bool = False) -> list[dict]:
        with self._trava:
            linhas = self._con.execute(
                "SELECT velha, nova, relacao, citacao_velha, citacao_nova, em, descartado FROM achados "
                + ("" if incluir_descartados else "WHERE descartado = 0 ") + "ORDER BY em DESC").fetchall()
        return [{"old": v, "new": n, "relation": r, "old_said": cv, "new_says": cn, "found_at": em,
                 "dismissed": bool(d)} for v, n, r, cv, cn, em, d in linhas]
