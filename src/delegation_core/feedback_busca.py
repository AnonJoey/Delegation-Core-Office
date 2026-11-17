"""Voto de utilidade em resultado de busca, e o caminho do voto ate a avaliacao.

Trazido do Paperclip (votos de feedback em saida de agente, exportados para
avaliacao). Aqui o alvo e o resultado de busca: o agente que usou (ou
descartou) uma fonte diz isso, e os votos viram duas coisas:

- um relatorio das fontes que mais decepcionam e das consultas sem acerto;
- perguntas de avaliacao (`avaliacao.py`) com o caminho votado como esperado,
  para que uma melhoria de busca seja medida contra uso real.

Grava em `search_feedback.jsonl`, so acrescentando. A consulta e guardada
porque e o que se avalia; passa pelo `segredos` antes.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path


def _arquivo() -> Path:
    from . import config
    return config.CONFIG_DIR / "search_feedback.jsonl"


def votar(consulta: str, caminho: str, voto: int, nota: str = "", cliente: str = "", escopo: str = "") -> dict:
    if voto not in (1, -1):
        raise ValueError("vote must be 1 (useful) or -1 (not useful)")
    if not consulta.strip() or not caminho.strip():
        raise ValueError("query and path are required")
    from .segredos import redigir
    consulta, _ = redigir(consulta.strip())
    nota, _ = redigir(nota.strip())
    reg = {"when": datetime.now().isoformat(timespec="seconds"), "query": consulta[:500],
           "path": caminho.strip(), "vote": voto, "note": nota[:500], "client": cliente, "scope": escopo}
    arq = _arquivo()
    arq.parent.mkdir(parents=True, exist_ok=True)
    with arq.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(reg, ensure_ascii=False) + "\n")
    return reg


def ler(dias: int = 0) -> list[dict]:
    arq = _arquivo()
    if not arq.is_file():
        return []
    corte = (datetime.now() - timedelta(days=dias)).isoformat() if dias else ""
    saida = []
    for linha in arq.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(linha)
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("when", "") >= corte:
            saida.append(r)
    return saida


def relatorio(dias: int = 30, top: int = 10) -> dict:
    votos = ler(dias)
    por_caminho = defaultdict(lambda: [0, 0])
    por_consulta = defaultdict(lambda: [0, 0])
    for v in votos:
        i = 0 if v["vote"] > 0 else 1
        por_caminho[v["path"]][i] += 1
        por_consulta[v["query"].lower()][i] += 1
    piores = sorted(((c, u, n) for c, (u, n) in por_caminho.items() if n > u), key=lambda x: (x[1] - x[2], x[0]))
    sem_acerto = sorted(q for q, (u, n) in por_consulta.items() if u == 0 and n > 0)
    return {
        "days": dias, "votes": len(votos),
        "useful": sum(1 for v in votos if v["vote"] > 0),
        "not_useful": sum(1 for v in votos if v["vote"] < 0),
        "worst_sources": [{"path": c, "useful": u, "not_useful": n} for c, u, n in piores[:top]],
        "queries_without_a_useful_result": sem_acerto[:top],
    }


def para_avaliacao(dias: int = 0) -> list[dict]:
    """Consultas com voto positivo, no formato de `avaliacao.carregar`.

    O caminho votado util vale grau 2; um caminho votado util mais de uma vez
    para a mesma consulta, grau 3. Voto negativo nao entra: "nao era isto" nao
    diz o que era.
    """
    contagem: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    original: dict[str, str] = {}
    for v in ler(dias):
        if v["vote"] > 0:
            chave = v["query"].lower()
            original.setdefault(chave, v["query"])
            contagem[chave][v["path"]] += 1
    return [{"pergunta": original[q], "esperado": {c: (3 if n > 1 else 2) for c, n in caminhos.items()}}
            for q, caminhos in sorted(contagem.items())]


def cmd_feedback(args) -> int:
    if args.acao == "report":
        print(json.dumps(relatorio(args.days), ensure_ascii=False, indent=2))
        return 0
    if args.acao == "export":
        dados = para_avaliacao(args.days)
        destino = Path(args.out).expanduser()
        if destino.exists() and not args.force:
            print(f"{destino} exists (use --force; your hand-written questions live there)")
            return 1
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{len(dados)} questions written to {destino}. Run: delegation-core eval-search {destino}")
        return 0
    return 1


def registrar(sub) -> dict:
    p = sub.add_parser("feedback", help="Search feedback votes: report, export to eval questions")
    s = p.add_subparsers(dest="acao", required=True)
    r = s.add_parser("report")
    r.add_argument("--days", type=int, default=30)
    e = s.add_parser("export")
    e.add_argument("out")
    e.add_argument("--days", type=int, default=0)
    e.add_argument("--force", action="store_true")
    return {"feedback": cmd_feedback}
