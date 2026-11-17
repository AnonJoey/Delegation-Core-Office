"""Avaliacao de busca: perguntas com resposta conhecida, medidas por escopo.

Veio do PR 23 do master e ganhou aqui o que a rubrica de busca do Paperclip
mede: relevancia graduada, nDCG@k, latencia e metas.

Cada consulta diz o que deveria voltar como trechos de caminho (`esperado`):
uma lista (todo trecho vale grau 1) ou um objeto `{trecho: grau}` com grau de
0 a 3. Para cada escopo saem:

  acertos@k   consultas com algum resultado relevante nos k primeiros
  mrr         media de 1/posicao do primeiro relevante (0 se nenhum)
  ndcg        nDCG@k com os graus; a ordem ideal e a dos graus informados
  latencia    p50 e p95 em milissegundos
  erros       perguntas sem acerto, com o que voltou no lugar

Metas padrao do Paperclip: MRR >= 0.95 e nDCG@5 >= 0.90. `abaixo_da_meta`
diz quem nao chegou; a CLI sai com 1 nesse caso, para servir de portao.

As perguntas ficam FORA do repositorio (citam pessoas e documentos do
usuario): `~/.delegation_core/avaliacao/consultas.json` por padrao.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

#: buscar(pergunta, escopo, k) -> caminhos dos resultados, em ordem.
Buscador = Callable[[str, str, int], list[str]]

META_MRR = 0.95
META_NDCG = 0.90


@dataclass
class Consulta:
    pergunta: str
    graus: dict[str, int]

    def __post_init__(self):
        # O contrato do PR 23 da producao e uma lista de trechos esperados
        # (relevancia binaria). Aceitar lista ou texto aqui mantem quem constroi
        # Consulta como no PR 23 funcionando: cada trecho listado vale grau 1.
        if isinstance(self.graus, str):
            self.graus = [self.graus]
        if isinstance(self.graus, (list, tuple)):
            self.graus = {t: 1 for t in self.graus}

    @property
    def esperado(self) -> list[str]:
        return [t for t, g in self.graus.items() if g > 0]


@dataclass
class ResultadoEscopo:
    escopo: str
    k: int
    total: int = 0
    acertos: int = 0
    soma_rr: float = 0.0
    soma_ndcg: float = 0.0
    tempos_ms: list[float] = field(default_factory=list)
    erros: list[dict] = field(default_factory=list)

    @property
    def mrr(self) -> float:
        return round(self.soma_rr / self.total, 3) if self.total else 0.0

    @property
    def ndcg(self) -> float:
        return round(self.soma_ndcg / self.total, 3) if self.total else 0.0

    def percentil(self, p: float) -> float:
        if not self.tempos_ms:
            return 0.0
        t = sorted(self.tempos_ms)
        return round(t[min(len(t) - 1, int(math.ceil(p * len(t))) - 1)], 1)

    def abaixo_da_meta(self, meta_mrr: float = META_MRR, meta_ndcg: float = META_NDCG) -> list[str]:
        falta = []
        if self.mrr < meta_mrr:
            falta.append(f"mrr {self.mrr} < {meta_mrr}")
        if self.ndcg < meta_ndcg:
            falta.append(f"ndcg@{self.k} {self.ndcg} < {meta_ndcg}")
        return falta

    def resumo(self) -> dict:
        return {"escopo": self.escopo, "k": self.k, "consultas": self.total,
                "acertos": self.acertos, "mrr": self.mrr, "ndcg": self.ndcg,
                "latencia_ms": {"p50": self.percentil(0.5), "p95": self.percentil(0.95)},
                "erros": self.erros}


def _graus(item: dict, i: int) -> dict[str, int]:
    esperado = item.get("esperado") or []
    if isinstance(esperado, str):
        esperado = [esperado]
    if isinstance(esperado, list):
        graus = {str(t): 1 for t in esperado if t}
    elif isinstance(esperado, dict):
        graus = {}
        for t, g in esperado.items():
            if not isinstance(g, int) or not 0 <= g <= 3:
                raise ValueError(f"consulta {i}: grau de {t!r} deve ser inteiro de 0 a 3")
            graus[str(t)] = g
    else:
        raise ValueError(f"consulta {i}: 'esperado' deve ser lista ou objeto")
    return graus


def carregar(caminho: str | Path) -> list[Consulta]:
    """Le o arquivo de consultas. Recusa consulta sem nenhum trecho relevante:
    uma consulta que nao diz o que conta como acerto so pode ser contada como erro."""
    dados = json.loads(Path(caminho).expanduser().read_text(encoding="utf-8"))
    consultas = []
    for i, item in enumerate(dados):
        graus = _graus(item, i)
        if not item.get("pergunta") or not any(g > 0 for g in graus.values()):
            raise ValueError(f"consulta {i} sem 'pergunta' ou sem 'esperado'")
        consultas.append(Consulta(item["pergunta"], graus))
    return consultas


def grau_de(caminho: str, graus: dict[str, int]) -> int:
    return max((g for t, g in graus.items() if t in (caminho or "")), default=0)


def posicao_do_acerto(caminhos: list[str], esperado: list[str] | dict) -> int:
    """Posicao (a partir de 1) do primeiro caminho relevante; 0 se nenhum."""
    graus = esperado if isinstance(esperado, dict) else {t: 1 for t in esperado}
    for pos, caminho in enumerate(caminhos, start=1):
        if grau_de(caminho, graus) > 0:
            return pos
    return 0


def ndcg(caminhos: list[str], graus: dict[str, int], k: int) -> float:
    """nDCG@k com ganho 2^g - 1. Cada trecho esperado conta uma vez so: dois
    resultados que casam o mesmo trecho nao somam duas vezes."""
    usados: set[str] = set()
    dcg = 0.0
    for pos, caminho in enumerate(caminhos[:k], start=1):
        melhor = None
        for t, g in sorted(graus.items(), key=lambda x: -x[1]):
            if g > 0 and t not in usados and t in (caminho or ""):
                melhor = (t, g)
                break
        if melhor:
            usados.add(melhor[0])
            dcg += (2 ** melhor[1] - 1) / math.log2(pos + 1)
    ideal = sorted((g for g in graus.values() if g > 0), reverse=True)[:k]
    idcg = sum((2 ** g - 1) / math.log2(pos + 1) for pos, g in enumerate(ideal, start=1))
    return dcg / idcg if idcg else 0.0


def avaliar(consultas: list[Consulta], buscar: Buscador, escopos: list[str],
            k: int = 5, relogio=time.perf_counter) -> list[ResultadoEscopo]:
    resultados = []
    for escopo in escopos:
        r = ResultadoEscopo(escopo=escopo, k=k)
        for c in consultas:
            t0 = relogio()
            caminhos = buscar(c.pergunta, escopo, k)[:k]
            r.tempos_ms.append((relogio() - t0) * 1000)
            pos = posicao_do_acerto(caminhos, c.graus)
            r.total += 1
            r.soma_ndcg += ndcg(caminhos, c.graus, k)
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


def arquivo_padrao() -> Path:
    from . import config
    return config.CONFIG_DIR / "avaliacao" / "consultas.json"


def cmd_eval_search(args) -> int:
    """Mede a busca pelo daemon; sai com 1 se algum escopo ficar abaixo da meta."""
    import sys
    from .config import Config
    from .daemon import DaemonUnavailable

    cfg = Config.load()
    try:
        consultas = carregar(args.arquivo or arquivo_padrao())
    except (OSError, ValueError) as e:
        print(f"Nao li as perguntas: {e}", file=sys.stderr)
        return 1
    escopos = [e.strip() for e in args.scope.split(",") if e.strip()]
    try:
        resultados = avaliar(consultas, buscador_do_daemon(cfg), escopos, k=args.k)
    except DaemonUnavailable as e:
        print(f"Daemon fora do ar: {e}", file=sys.stderr)
        return 1
    falhou = any(r.abaixo_da_meta(args.min_mrr, args.min_ndcg) for r in resultados) if args.gate else False
    if args.json:
        print(json.dumps([r.resumo() for r in resultados], ensure_ascii=False, indent=2))
        return 1 if falhou else 0
    for r in resultados:
        print(f"{r.escopo:16s} acertos@{r.k} {r.acertos}/{r.total}  mrr {r.mrr}  ndcg {r.ndcg}  "
              f"p50 {r.percentil(0.5)}ms p95 {r.percentil(0.95)}ms")
        for erro in r.erros:
            print(f"    x {erro['pergunta']}")
        if args.gate:
            for f in r.abaixo_da_meta(args.min_mrr, args.min_ndcg):
                print(f"    abaixo da meta: {f}")
    return 1 if falhou else 0


def registrar(sub) -> dict:
    p = sub.add_parser("eval-search", help="Measure search on known-answer questions: hits, MRR, nDCG, latency")
    p.add_argument("arquivo", nargs="?", default="", help="questions JSON (default ~/.delegation_core/avaliacao/consultas.json)")
    p.add_argument("--scope", default="notes,all", help="comma-separated scopes")
    p.add_argument("-k", type=int, default=5)
    p.add_argument("--json", action="store_true")
    p.add_argument("--gate", action="store_true", help="exit 1 when a scope is below the targets")
    p.add_argument("--min-mrr", type=float, default=META_MRR)
    p.add_argument("--min-ndcg", type=float, default=META_NDCG)
    return {"eval-search": cmd_eval_search}
