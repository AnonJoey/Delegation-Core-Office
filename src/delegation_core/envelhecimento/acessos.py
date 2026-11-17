"""Contadores de uso das notas: quantas vezes foi lida, quando foi a ultima, e a saliencia votada.

Equivale as colunas `access_count`, `last_accessed_at` e `salience` da tabela `pages` do
ai-memory (MIT, Fabio Akita), que alimentam a retencao. Aqui sao uma tabela propria em
sqlite, porque as notas do cofre sao markdown puro e nao tem onde guardar contador.

O caminho da nota e a chave. Renomear uma nota leva o contador junto (`renomear`), e esquecer
uma nota leva o contador embora (`esquecer`). Restaurar uma nota conta como uma leitura
(`envelhecimento_vault.registrar_leituras`): a nota que alguem foi buscar no historico ganha
algumas semanas antes de esfriar de novo, em vez de ser compactada outra vez no dia seguinte.
Se a nota ja foi compactada nao e este banco que sabe: e o `compacted: true` do frontmatter.

Pacote independente: so a biblioteca padrao e `retencao`.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

from .retencao import Parametros, saliencia_depois_do_voto

VOTOS = ("helpful", "not_helpful", "stale", "wrong")


def _agora_us() -> int:
    return time.time_ns() // 1000


class Acessos:
    def __init__(self, caminho: str | Path):
        self.caminho = Path(caminho)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self._trava = threading.RLock()
        self._con = sqlite3.connect(str(self.caminho), check_same_thread=False, isolation_level=None, timeout=5.0)
        self._con.row_factory = sqlite3.Row
        self._con.executescript(
            """
            PRAGMA journal_mode = WAL;
            PRAGMA busy_timeout = 5000;
            CREATE TABLE IF NOT EXISTS acessos (
                nota TEXT PRIMARY KEY, total INTEGER NOT NULL DEFAULT 0,
                ultimo_us INTEGER, saliencia REAL
            );
            """
        )

    def fechar(self) -> None:
        with self._trava:
            self._con.close()

    def registrar(self, nota: str, agora_us: int | None = None, vezes: int = 1) -> None:
        """Uma leitura (ou `vezes`): soma ao total e atualiza o instante do ultimo acesso."""
        if vezes < 1:
            return
        em = _agora_us() if agora_us is None else agora_us
        with self._trava:
            self._con.execute(
                "INSERT INTO acessos(nota, total, ultimo_us) VALUES (?, ?, ?)"
                " ON CONFLICT(nota) DO UPDATE SET total = total + excluded.total,"
                " ultimo_us = MAX(COALESCE(ultimo_us, 0), excluded.ultimo_us)",
                (nota, vezes, em))

    def votar(self, nota: str, voto: str, p: Parametros, agora_us: int | None = None) -> float:
        """`record_feedback`: move a saliencia um degrau (ou ao piso, para stale e wrong). Devolve a nova."""
        if voto not in VOTOS:
            raise ValueError(f"voto desconhecido: {voto!r}")
        with self._trava:
            self._con.execute("BEGIN IMMEDIATE")
            try:
                linha = self._con.execute("SELECT saliencia FROM acessos WHERE nota = ?", (nota,)).fetchone()
                atual = None if linha is None else linha["saliencia"]
                nova = saliencia_depois_do_voto(p, atual, voto)
                self._con.execute(
                    "INSERT INTO acessos(nota, saliencia) VALUES (?, ?)"
                    " ON CONFLICT(nota) DO UPDATE SET saliencia = excluded.saliencia", (nota, nova))
                self._con.execute("COMMIT")
            except BaseException:
                self._con.execute("ROLLBACK")
                raise
        return nova

    def obter(self, nota: str) -> dict | None:
        with self._trava:
            linha = self._con.execute("SELECT * FROM acessos WHERE nota = ?", (nota,)).fetchone()
        return None if linha is None else dict(linha)

    def todas(self) -> dict[str, dict]:
        with self._trava:
            return {x["nota"]: dict(x) for x in self._con.execute("SELECT * FROM acessos").fetchall()}

    def renomear(self, antiga: str, nova: str) -> bool:
        """Leva o contador para o caminho novo. Se o novo ja tinha contador, soma os totais e fica o acesso mais recente."""
        with self._trava:
            self._con.execute("BEGIN IMMEDIATE")
            try:
                a = self._con.execute("SELECT * FROM acessos WHERE nota = ?", (antiga,)).fetchone()
                if a is None:
                    self._con.execute("COMMIT")
                    return False
                n = self._con.execute("SELECT * FROM acessos WHERE nota = ?", (nova,)).fetchone()
                if n is None:
                    self._con.execute("UPDATE acessos SET nota = ? WHERE nota = ?", (nova, antiga))
                else:
                    ultimos = [v for v in (a["ultimo_us"], n["ultimo_us"]) if v is not None]
                    self._con.execute(
                        "UPDATE acessos SET total = ?, ultimo_us = ?, saliencia = COALESCE(saliencia, ?) WHERE nota = ?",
                        (a["total"] + n["total"], max(ultimos) if ultimos else None, a["saliencia"], nova))
                    self._con.execute("DELETE FROM acessos WHERE nota = ?", (antiga,))
                self._con.execute("COMMIT")
                return True
            except BaseException:
                self._con.execute("ROLLBACK")
                raise

    def esquecer(self, nota: str) -> bool:
        with self._trava:
            return self._con.execute("DELETE FROM acessos WHERE nota = ?", (nota,)).rowcount > 0
