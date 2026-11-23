"""Livro-caixa de uso: cada chamada de ferramenta, com o que entrou, o que saiu e quanto demorou.

## Por que existe

O delegation-core existe para que o agente gaste menos, e nada media isso. A
tese do projeto ("empurre o trabalho para ele, custo marginal zero") era dita,
nao contada. O proc_d3941c herdou uma meta sem instrumento: medir o consumo de
tokens delegando contra a linha de base de ~70k da v1 feita a mao.

O paperclip guarda politica e incidente de orcamento por agente
(`packages/db/src/schema/budget_policies.ts`, `budget_incidents.ts`) e
telemetria por comando (`src/telemetry.ts`). Este modulo e o livro que torna
esse tipo de conta possivel aqui.

## O que e medido, e o que e estimado

Medido, por chamada: ferramenta, cliente, duracao, caracteres dos argumentos,
caracteres da resposta, se foi erro, e `chars_apontados`: o tamanho das notas
que a resposta aponta (os `sources` de uma busca). Desde 23/11/2026 (6.1.3), tambem
`espera`: quantos segundos a chamada ficou na fila do pool de compressao antes de
um worker pegar. Nulo quando nao houve fila a medir (a ferramenta nao comprime, ou a
linha e de antes da coluna): nulo nao e zero. Estimado, e dito como tal
no relatorio: tokens = caracteres / 4. `chars_apontados` e um TETO do que o
agente leria sem a ferramenta, nao a economia: ele nao leria todas as notas
apontadas inteiras, mas tambem nao saberia quais ler.

## Criterio de lego

sqlite3 e statistics. Recebe numeros, devolve agregados. Nao sabe o que e MCP.
"""

from __future__ import annotations

import sqlite3
import statistics
import threading
import time
from pathlib import Path

CHARS_POR_TOKEN = 4


class LivroCaixa:
    def __init__(self, caminho: str | Path):
        self.caminho = Path(caminho)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self._trava = threading.Lock()
        self._con = sqlite3.connect(str(self.caminho), check_same_thread=False)
        self._con.executescript(
            """
            PRAGMA journal_mode = WAL;
            CREATE TABLE IF NOT EXISTS chamadas (
                em REAL NOT NULL, ferramenta TEXT NOT NULL, cliente TEXT NOT NULL DEFAULT '',
                segundos REAL NOT NULL, chars_entrada INTEGER NOT NULL, chars_saida INTEGER NOT NULL,
                chars_apontados INTEGER NOT NULL DEFAULT 0, erro TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS chamadas_em ON chamadas(em);
            """
        )
        colunas = {linha[1] for linha in self._con.execute("PRAGMA table_info(chamadas)")}
        if "espera" not in colunas:
            # Aditiva: o livro de antes continua valendo, com as linhas antigas sem espera (nulo).
            self._con.execute("ALTER TABLE chamadas ADD COLUMN espera REAL")
            self._con.commit()

    def fechar(self) -> None:
        with self._trava:
            self._con.close()

    def registrar(self, ferramenta: str, segundos: float, chars_entrada: int, chars_saida: int,
                  cliente: str = "", chars_apontados: int = 0, erro: str = "", em: float | None = None,
                  espera: float | None = None) -> None:
        with self._trava, self._con:
            self._con.execute(
                "INSERT INTO chamadas (em, ferramenta, cliente, segundos, chars_entrada, chars_saida, "
                "chars_apontados, erro, espera) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (time.time() if em is None else em, ferramenta, cliente or "", float(segundos),
                 int(chars_entrada), int(chars_saida), int(chars_apontados), erro or "",
                 None if espera is None else float(espera)),
            )

    def relatorio(self, desde: float = 0.0) -> dict:
        with self._trava:
            linhas = self._con.execute(
                "SELECT ferramenta, cliente, segundos, chars_entrada, chars_saida, chars_apontados, erro, espera "
                "FROM chamadas WHERE em >= ?", (desde,)).fetchall()
        por: dict[str, dict] = {}
        clientes: dict[str, int] = {}
        for f, cli, s, ce, cs, ca, e, esp in linhas:
            d = por.setdefault(f, {"ferramenta": f, "chamadas": 0, "erros": 0, "_seg": [], "_esp": [],
                                   "chars_entrada": 0, "chars_saida": 0, "chars_apontados": 0})
            d["chamadas"] += 1
            if esp is not None:
                d["_esp"].append(esp)
            d["erros"] += 1 if e else 0
            d["_seg"].append(s)
            d["chars_entrada"] += ce
            d["chars_saida"] += cs
            d["chars_apontados"] += ca
            clientes[cli or "?"] = clientes.get(cli or "?", 0) + 1
        ferramentas = []
        for d in por.values():
            seg = sorted(d.pop("_seg"))
            d["segundos_p50"] = round(statistics.median(seg), 3)
            d["segundos_p95"] = round(seg[min(len(seg) - 1, int(0.95 * len(seg)))], 3)
            d["segundos_total"] = round(sum(seg), 1)
            esp = sorted(d.pop("_esp"))
            if esp:
                # So as chamadas que passaram pela fila do pool; as outras nao tem espera a medir.
                d["espera_medida_em"] = len(esp)
                d["espera_p50"] = round(statistics.median(esp), 3)
                d["espera_p95"] = round(esp[min(len(esp) - 1, int(0.95 * len(esp)))], 3)
                d["espera_max"] = round(esp[-1], 3)
            ferramentas.append(d)
        ferramentas.sort(key=lambda d: (-d["chamadas"], d["ferramenta"]))
        tot_saida = sum(d["chars_saida"] for d in ferramentas)
        tot_apont = sum(d["chars_apontados"] for d in ferramentas)
        return {
            "chamadas": len(linhas),
            "clientes": clientes,
            "ferramentas": ferramentas,
            "tokens_entregues_estimados": tot_saida // CHARS_POR_TOKEN,
            "tokens_apontados_teto": tot_apont // CHARS_POR_TOKEN,
            "estimativa": f"tokens = caracteres / {CHARS_POR_TOKEN}. 'apontados' e o tamanho das notas "
                          "que as respostas indicam: teto do que se leria sem a ferramenta, nao economia.",
        }
