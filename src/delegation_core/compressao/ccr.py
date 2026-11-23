"""Guarda reversivel (CCR do Headroom): o original fica, o comprimido aponta para ele.

O Headroom chama de CCR (Compress-Cache-Retrieve): quando uma compressao perde
linhas, o texto inteiro vai para um armazenamento com chave (md5, 24 hex) e o
comprimido termina com `Retrieve more: hash=<chave>`. Aqui o armazenamento e a
mesma base do `filtros_saida` (`saidas.sqlite3`), numa tabela propria, e
`recall_output` le as duas.
"""

from __future__ import annotations

import time

from ..filtros_saida import execucao


class Guarda:
    """O `CcrStore` do Headroom: put(chave, conteudo) e get(chave)."""

    def _con(self):
        c = execucao._con()
        c.execute("CREATE TABLE IF NOT EXISTS ccr (chave TEXT PRIMARY KEY, conteudo TEXT, criado REAL)")
        return c

    def put(self, chave: str, conteudo: str) -> None:
        if execucao._COLETOR is not None:
            # Worker do pool: quem grava e o daemon, quando o resultado volta (6.1.2).
            execucao._COLETOR.append((chave, conteudo))
            return
        if not execucao.e_escritor():
            from .. import cliente_fino
            if cliente_fino.guardar_ccr(chave, conteudo):
                return
        with execucao._TRAVA:
            c = self._con()
            c.execute("INSERT OR REPLACE INTO ccr VALUES (?, ?, ?)", (chave, conteudo, time.time()))
            c.commit()

    def get(self, chave: str) -> str | None:
        with execucao._TRAVA:
            linha = self._con().execute("SELECT conteudo FROM ccr WHERE chave = ?", (chave,)).fetchone()
        return linha[0] if linha else None
