"""Catalogo dos erros que um agente ou uma pessoa pode ver, gerado do codigo.

Trazido do REA (`docs/user-visible-errors.csv`): cada erro visivel, onde nasce,
o texto, e um risco, em ordem de dano. Aqui e GERADO a partir de `server.py`
(toda chamada `erros.*` dentro de uma ferramenta MCP) e conferido por teste:
o CSV em `docs/erros-visiveis.csv` nao pode ficar velho.

Risco, do maior para o menor:
1. erro que diz que da para consertar (`missing_dependency`, `disabled`) mas
   nao diz como: a regra do proprio `erros.dependencia_ausente`;
2. `failure`: ninguem sabe o que houve;
3. `unavailable`, `invalid_input`, `not_found`, nessa ordem.
"""

from __future__ import annotations

import ast
import csv
import io
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SERVER = Path(__file__).resolve().parent / "server.py"
DOC = RAIZ / "docs" / "erros-visiveis.csv"

_CATEGORIA = {
    "nao_encontrado": "not_found", "dependencia_ausente": "missing_dependency", "desligado": "disabled",
    "entrada_invalida": "invalid_input", "indisponivel": "unavailable", "falha": "failure",
}
_ORDEM = {"failure": 2, "unavailable": 3, "invalid_input": 4, "not_found": 5,
          "missing_dependency": 6, "disabled": 6}
_REMEDIO = re.compile(r"(\brun\b|pip install|delegation-core |\bset \w+|\buse \w|\bcall \w|\bpass \w|"
                      r"=true|=false|\bre-?read\b|\bretry\b|\bvalid\b|must|:\s*\w+\|)", re.I)


def _texto(no: ast.AST, fonte: str) -> str:
    if isinstance(no, ast.Constant) and isinstance(no.value, str):
        return no.value
    if isinstance(no, ast.JoinedStr):
        partes = []
        for v in no.values:
            if isinstance(v, ast.Constant):
                partes.append(str(v.value))
            else:
                partes.append("{" + (ast.get_source_segment(fonte, v.value) or "?") + "}")
        return "".join(partes)
    if isinstance(no, ast.BinOp) and isinstance(no.op, ast.Add):
        return _texto(no.left, fonte) + _texto(no.right, fonte)
    return "{" + (ast.get_source_segment(fonte, no) or "?") + "}"


def linhas() -> list[dict]:
    fonte = SERVER.read_text(encoding="utf-8")
    arvore = ast.parse(fonte)
    saida = []
    for func in ast.walk(arvore):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for no in ast.walk(func):
            if (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
                    and isinstance(no.func.value, ast.Name) and no.func.value.id == "erros"
                    and no.func.attr in _CATEGORIA and no.args):
                cat = _CATEGORIA[no.func.attr]
                msg = " ".join(_texto(no.args[0], fonte).split())
                remedio = bool(_REMEDIO.search(msg))
                saida.append({"function": func.name, "line": no.lineno, "error_type": cat,
                              "retryable": cat == "unavailable", "has_remedy": remedio, "message": msg})
    unicos = {}
    for l in saida:  # a funcao de fora (a ferramenta) vence a aninhada
        unicos.setdefault(l["line"], l)
    unicos = unicos.values()

    def dano(l):
        sem_conserto = l["error_type"] in ("missing_dependency", "disabled") and not l["has_remedy"]
        return (1 if sem_conserto else _ORDEM[l["error_type"]], l["function"], l["line"])
    ordenadas = sorted(unicos, key=dano)
    for n, l in enumerate(ordenadas, start=1):
        l["harm_rank"] = n
    return ordenadas


def gerar_csv() -> str:
    buf = io.StringIO()
    campos = ["harm_rank", "function", "line", "error_type", "retryable", "has_remedy", "message"]
    w = csv.DictWriter(buf, fieldnames=campos, lineterminator="\n")
    w.writeheader()
    for l in linhas():
        w.writerow({k: l[k] for k in campos})
    return buf.getvalue()


def cmd_errors_catalog(args) -> int:
    texto = gerar_csv()
    if args.write:
        DOC.write_text(texto, encoding="utf-8")
        print(f"{DOC} rewritten ({texto.count(chr(10)) - 1} errors)")
    else:
        print(texto, end="")
    return 0


def registrar(sub) -> dict:
    p = sub.add_parser("errors-catalog", help="Every user-visible MCP error, ranked by harm (CSV)")
    p.add_argument("--write", action="store_true", help="rewrite docs/erros-visiveis.csv in the source tree")
    return {"errors-catalog": cmd_errors_catalog}


if __name__ == "__main__":  # python -m delegation_core.catalogo_erros > docs/erros-visiveis.csv
    print(gerar_csv(), end="")
