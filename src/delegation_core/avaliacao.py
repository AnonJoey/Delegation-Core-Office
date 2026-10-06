"""Avaliacao de busca: perguntas com resposta conhecida, medidas por escopo.

Cada consulta diz o que deveria voltar como trechos de caminho aceitos
(`esperado`). Uma consulta acerta em k quando algum dos k primeiros resultados
tem um caminho que contem algum desses trechos. Para cada escopo saem:

  acertos@k   quantas consultas acertaram
  mrr         media de 1/posicao do primeiro acerto (0 quando nao acerta)
  erros       as perguntas que nao acertaram, para ler o que voltou no lugar

Por que existe: em 05/10/2026 a busca padrao desta maquina respondeu
"quem e o contato da Anthropic..." com tres transcricoes sem relacao, enquanto
scope='all' trazia os tres documentos certos. Sem um conjunto fixo de
perguntas, "melhorou" e "piorou" ficam na impressao de quem testou duas vezes.

As perguntas ficam FORA do repositorio (elas citam pessoas e documentos do
usuario). Este modulo so le o arquivo indicado.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

#: buscar(pergunta, escopo, k) -> caminhos dos resultados, em ordem.
Buscador = Callable[[str, str, int], list[str]]


@dataclass
class Consulta:
    pergunta: str
    esperado: list[str]


@dataclass
class ResultadoEscopo:
    escopo: str
    k: int
    total: int = 0
    acertos: int = 0
    soma_rr: float = 0.0
    erros: list[dict] = field(default_factory=list)

    @property
    def mrr(self) -> float:
        return round(self.soma_rr / self.total, 3) if self.total else 0.0

    def resumo(self) -> dict:
        return {"escopo": self.escopo, "k": self.k, "consultas": self.total,
                "acertos": self.acertos, "mrr": self.mrr, "erros": self.erros}


def carregar(caminho: str | Path) -> list[Consulta]:
    """Le o arquivo de consultas. Recusa entrada sem `esperado`: uma consulta
    que nao diz o que conta como acerto so pode ser contada como erro."""
    dados = json.loads(Path(caminho).expanduser().read_text(encoding="utf-8"))
    consultas = []
    for i, item in enumerate(dados):
        esperado = item.get("esperado") or []
        if isinstance(esperado, str):
            esperado = [esperado]
        if not item.get("pergunta") or not esperado:
            raise ValueError(f"consulta {i} sem 'pergunta' ou sem 'esperado'")
        consultas.append(Consulta(item["pergunta"], list(esperado)))
    return consultas


def posicao_do_acerto(caminhos: list[str], esperado: list[str]) -> int:
    """Posicao (a partir de 1) do primeiro caminho que contem um esperado; 0 se nenhum."""
    for pos, caminho in enumerate(caminhos, start=1):
        if any(trecho in (caminho or "") for trecho in esperado):
            return pos
    return 0


def avaliar(consultas: list[Consulta], buscar: Buscador, escopos: list[str],
            k: int = 5) -> list[ResultadoEscopo]:
    resultados = []
    for escopo in escopos:
        r = ResultadoEscopo(escopo=escopo, k=k)
        for c in consultas:
            caminhos = buscar(c.pergunta, escopo, k)[:k]
            pos = posicao_do_acerto(caminhos, c.esperado)
            r.total += 1
            if pos:
                r.acertos += 1
                r.soma_rr += 1.0 / pos
            else:
                r.erros.append({"pergunta": c.pergunta, "voltou": caminhos[:3]})
        resultados.append(r)
    return resultados


def buscador_do_daemon(cfg) -> Buscador:
    """Busca pelo daemon em execucao, nunca abrindo o indice num segundo processo."""
    from .daemon import call_tool

    def buscar(pergunta: str, escopo: str, k: int) -> list[str]:
        resposta = call_tool(cfg, "search_vault",
                             {"query": pergunta, "scope": escopo, "limit": k, "snippet_chars": 1})
        if isinstance(resposta, str):
            resposta = json.loads(resposta)
        return [s.get("path", "") for s in (resposta.get("sources") or [])]

    return buscar
