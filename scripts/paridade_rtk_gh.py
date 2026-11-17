"""Paridade do porte de `gh pr` (e do `compact_diff`) com o binario real do RTK.

Uso: RTK_BIN=/caminho/rtk python scripts/paridade_rtk_gh.py [-n N] [-v]

O `gh` precisa de rede e de uma conta, entao o oraculo roda sobre um `gh` falso:
um executavel que ignora os argumentos e imprime a saida gravada (stdout, stderr)
e sai com o codigo dado, como em `paridade_rtk_modulos.py`. O RTK e o porte rodam
o mesmo falso e a saida dos dois, byte a byte, tem que ser igual.

`gh pr diff` entrega o texto cru a `compact_diff`, por isso este script tambem e o
oraculo do `compact_diff` com diffs sinteticos: de arquivo novo e de renomeacao,
combinados (`diff --cc`), com caminhos entre aspas, corpo com `+`/`-` no conteudo,
envelope de mbox, hunks de mais de 100 linhas, UTF-8 e `\\ No newline`.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import stat
import string
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from delegation_core.filtros_saida.modulos import base  # noqa: E402
from delegation_core.filtros_saida.modulos.ambiente import Ambiente  # noqa: E402
from delegation_core.filtros_saida.modulos.git import gh  # noqa: E402

RTK = os.environ.get("RTK_BIN", "rtk")
AVISO_DO_RTK = b"[rtk] /!\\ No hook installed"


def _p(r, a=3, b=9):
    return "".join(r.choice(string.ascii_lowercase) for _ in range(r.randint(a, b)))


def _frase(r, n=(2, 12)):
    return " ".join(_p(r) for _ in range(r.randint(*n)))


# ── geradores ────────────────────────────────────────────────────────────────

CAMINHOS_ESQUISITOS = ['src/a.py', 'src/com espaco/b.py', '"src/a\\303\\247\\303\\243o.py"', 'x b/y b/z.txt',
                       'docs/README.md', '"tab\\there.txt"', 'sem-barra.txt', 'src/é.py']
CONTEUDOS = ["", "+", "-", "++", "--", "+++ b/x", "--- a/x", "\\ No newline at end of file", "@@ -1 +1 @@",
             "diff --git a/x b/x", "texto normal", "  indentado", "éão", "\U0001F600 emoji",
             "-- ", "From abc Mon Sep 17 00:00:00 2001", "Subject: [PATCH] x"]


def _hunk(r):
    novas = r.choice([0, 1, 2, 3, 5, 8, 20, 120, 150])
    antigas = r.choice([0, 1, 2, 3, 5, 8, 20, 120, 150])
    corpo = []
    contexto = r.randint(0, 4)
    corpo += [" " + _frase(r, (1, 6)) for _ in range(contexto)]
    for _ in range(antigas):
        corpo.append("-" + (_frase(r) if r.random() < .9 else r.choice(CONTEUDOS)))
    for _ in range(novas):
        corpo.append("+" + (_frase(r) if r.random() < .9 else r.choice(CONTEUDOS)))
    meio = r.randint(0, 5)
    corpo += [" " + _frase(r, (1, 6)) for _ in range(meio)]
    if r.random() < .15:
        corpo.insert(r.randint(0, len(corpo)), "\\ No newline at end of file")
    conta_a = contexto + antigas + meio
    conta_n = contexto + novas + meio
    if r.random() < .08:
        conta_a += r.choice([-1, 1, 3])
        conta_a = max(conta_a, 0)
    cab = f"@@ -{r.randint(1, 999)},{conta_a} +{r.randint(1, 999)},{conta_n} @@"
    if r.random() < .5:
        cab = cab.replace(f",{conta_a} ", " ") if conta_a == 1 else cab
    if r.random() < .5:
        cab += " " + _frase(r, (1, 5))
    return [cab, *corpo]


def _combinado(r):
    pais = 2
    corpo = []
    for _ in range(r.randint(1, 20)):
        marca = r.choice(["  ", "+ ", " +", "- ", " -", "++", "--", "+-", "-+", "  "])
        corpo.append(marca + _frase(r, (1, 6)))
    a, b, c = r.randint(1, 50), r.randint(1, 50), r.randint(1, 50)
    return ["@@@ -%d,%d -%d,%d +%d,%d @@@" % (a, len(corpo), b, len(corpo), c, len(corpo)), *corpo][:1 + len(corpo)], pais


def diff_sintetico(r: random.Random) -> str:
    linhas: list[str] = []
    if r.random() < .15:
        linhas += ["From 1234abcd Mon Sep 17 00:00:00 2001", "From: A <a@b.c>", "Subject: [PATCH] algo", "", "corpo", "---",
                   " x | 1 +", " 1 file changed, 1 insertion(+)", ""]
    for _ in range(r.randint(0, 6)):
        caminho = r.choice(CAMINHOS_ESQUISITOS) if r.random() < .6 else f"src/{_p(r)}/{_p(r)}.py"
        tipo = r.random()
        if tipo < .12:
            linhas += [f"diff --cc {caminho}", "index 111,222..333", f"--- a/{caminho}", f"+++ b/{caminho}"]
            cab, _pais = _combinado(r)
            linhas += cab
            continue
        if tipo < .2:
            origem, destino = r.choice(CAMINHOS_ESQUISITOS), r.choice(CAMINHOS_ESQUISITOS)
            linhas += [f"diff --git a/{origem} b/{destino}", "similarity index 90%", f"rename from {origem}",
                       f"rename to {destino}"]
        else:
            linhas += [f"diff --git a/{caminho} b/{caminho}"]
        if r.random() < .2:
            linhas += ["new file mode 100644"]
        linhas += ["index abc..def 100644", f"--- a/{caminho}", f"+++ b/{caminho}"]
        for _ in range(r.randint(0, 4)):
            linhas += _hunk(r)
    if r.random() < .1:
        linhas += ["-- ", "2.43.0", ""]
    if r.random() < .08:
        linhas = [l + "\r" for l in linhas]
    fim = "\n" if r.random() < .85 else ""
    return "\n".join(linhas) + fim


def checks_sintetico(r: random.Random) -> str:
    estados = ["pass", "fail", "pending", "skipping", "cancel", "*", "weird", ""]
    nomes = [f"job-{_p(r, 2, 5)}" for _ in range(r.randint(1, 5))]
    saida = []
    for _ in range(r.randint(0, 3)):  # --watch repete a tabela
        for n in nomes:
            if r.random() < .2:
                continue
            saida.append("\t".join([n, r.choice(estados), f"{r.randint(0, 9)}m{r.randint(0, 59)}s",
                                    f"https://github.com/x/y/runs/{r.randint(1, 9)}", ""][:r.choice([2, 3, 4, 5, 5, 5])]))
    if r.random() < .1:
        saida.append("")
    if r.random() < .1:
        saida.append("sem tabulacao")
    return "\n".join(saida) + ("\n" if r.random() < .9 else "")


CORPOS_MD = ["", "texto simples\n", "<!-- comentario -->\n\ntexto\n", "[![badge](http://a)](http://b)\n",
             "![img](http://x.png)\n", "---\n", "```\ncodigo <!-- fica -->\n```\n", "~~~\n![i](x)\n~~~\n",
             "antes\n```py\nx\n```\ndepois\n\n\n\nmuito branco\n", "```\nsem fechar\n", "***\n___\n",
             "a\r\n\r\nb\r\n", "éão \U0001F600\n", "- item\n- item\n"]


def pr_json(r: random.Random, campos: str) -> str:
    def autor():
        return {"login": _p(r)} if r.random() < .9 else (None if r.random() < .5 else {})
    def checks():
        return [{"conclusion": r.choice(["SUCCESS", "FAILURE", "SKIPPED", None]), "state": r.choice(["SUCCESS", "FAILURE", None])}
                for _ in range(r.randint(0, 6))]
    def um():
        d = {"number": r.randint(1, 5000) if r.random() < .95 else r.choice([None, "x", 1.5, True]),
             "title": _frase(r, (1, 20)) if r.random() < .95 else None,
             "state": r.choice(["OPEN", "MERGED", "CLOSED", "DRAFT", None]),
             "author": autor(), "updatedAt": "2026-01-01T00:00:00Z",
             "url": f"https://github.com/x/y/pull/{r.randint(1, 99)}", "mergeable": r.choice(["MERGEABLE", "CONFLICTING", "UNKNOWN", None]),
             "body": "".join(r.sample(CORPOS_MD, r.randint(0, 4))) if r.random() < .8 else None,
             "reviews": {"nodes": [{"state": r.choice(["APPROVED", "CHANGES_REQUESTED", "COMMENTED"])} for _ in range(r.randint(0, 4))]}
             if r.random() < .8 else None,
             "statusCheckRollup": checks() if r.random() < .85 else None,
             "reviewDecision": r.choice(["APPROVED", "REVIEW_REQUIRED", "CHANGES_REQUESTED", None])}
        if r.random() < .1:
            for k in r.sample(list(d), 3):
                d.pop(k)
        return d
    if "list" in campos:
        return json.dumps([um() for _ in range(r.choice([0, 1, 3, 19, 20, 21, 35]))])
    if "status" in campos:
        d = {"currentBranch": um() if r.random() < .6 else None,
             "createdBy": [um() for _ in range(r.randint(0, 8))] if r.random() < .9 else None}
        if r.random() < .1:
            d.pop("currentBranch")
        return json.dumps(d)
    return json.dumps(um())


def casos(r: random.Random):
    """(args, stdout, stderr, codigo) de um caso sorteado."""
    familia = r.choice(["diff", "diff", "diff", "checks", "list", "view", "status", "create", "comment", "edit",
                        "merge", "falha", "json", "outro"])
    err = ""
    if r.random() < .12:
        err = "".join(f"aviso {i}: {_frase(r)}\n" for i in range(r.choice([1, 3, 12, 40])))
    if familia == "diff":
        extra = r.choice([[], [], ["123"], ["--color=never"], ["--no-compact"], ["--stat"], ["--patch"], ["--name-only"]])
        return ["pr", "diff", *extra], diff_sintetico(r) if r.random() < .93 else "", err, 0
    if familia == "checks":
        return ["pr", "checks", *r.choice([[], ["12"], ["--watch"], ["-R", "x/y", "12"], ["12", "-R", "x/y"]])], checks_sintetico(r), err, r.choice([0, 0, 8, 1])
    if familia == "list":
        return ["pr", "list", *r.choice([[], ["--state", "all"], ["-L", "50"]])], pr_json(r, "list") if r.random() < .95 else "nao e json", err, 0
    if familia == "view":
        return ["pr", "view", *r.choice([[], ["12"], ["12", "-R", "x/y"], ["--web"], ["12", "--comments"], ["12", "--jq", ".x"]])], \
            pr_json(r, "view") if r.random() < .95 else "nao e json", err, 0
    if familia == "status":
        return ["pr", "status", *r.choice([[], [], ["--web"], ["--jq", ".x"], ["-R", "x/y"]])], pr_json(r, "status"), err, 0
    if familia == "create":
        url = r.choice([f"https://github.com/x/y/pull/{r.randint(1, 999)}", "https://github.com/x/y/pull/abc", "", "texto qualquer"])
        return ["pr", "create", "--title", "t", "--body", "b"], url + "\n", err, r.choice([0, 0, 1])
    if familia in ("comment", "edit"):
        return ["pr", familia, *r.choice([["12"], ["12", "--body", "x"], ["--body", "x"], ["-b", "x", "7"], []])], r.choice(["", "https://github.com/x/y/pull/1#c\n"]), err, r.choice([0, 0, 1])
    if familia == "merge":
        return ["pr", "merge", "12", "--squash"], "Merged\n", err, r.choice([0, 1])
    if familia == "falha":
        return ["pr", r.choice(["list", "view", "diff", "status", "create"])], r.choice(["", "saida\n"]), "erro: " + _frase(r) + "\n", r.choice([1, 2, 4])
    if familia == "json":
        return ["pr", "view", "12", "--json", "title"], '{"title":"x"}\n', err, 0
    # `issue`, `run`, `repo` e `api` o RTK filtra e o porte nao: ficam fora. O resto de `pr` passa direto.
    return ["pr", r.choice(["ready", "close", "reopen", "checkout", "lock"]), *r.choice([[], ["12"]])], "saida\n", err, r.choice([0, 1])


# ── execucao ─────────────────────────────────────────────────────────────────

def falso(dirb: Path, stdout: str, stderr: str, codigo: int) -> None:
    (dirb / "gh.out").write_bytes(stdout.encode())
    (dirb / "gh.err").write_bytes(stderr.encode())
    p = dirb / "gh"
    p.write_text(f'#!/bin/sh\ncat "{dirb}/gh.out"\ncat "{dirb}/gh.err" >&2\nexit {codigo}\n')
    p.chmod(p.stat().st_mode | stat.S_IEXEC)


def _limpa(stderr: bytes) -> bytes:
    return b"".join(l for l in stderr.splitlines(keepends=True) if not l.startswith(AVISO_DO_RTK))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=600)
    ap.add_argument("-v", action="store_true")
    a = ap.parse_args()
    base.PREFIXO = "rtk"
    ok = 0
    falhas = []
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        dirb, casa, trab = t / "bin", t / "casa", t / "trab"
        for d in (dirb, casa, trab):
            d.mkdir()
        env = {"PATH": f"{dirb}:/usr/bin:/bin", "HOME": str(casa), "NO_COLOR": "1", "RTK_NO_TRACK": "1",
               "XDG_DATA_HOME": str(casa / "share"), "XDG_CONFIG_HOME": str(casa / "config"), "LANG": "C.UTF-8"}
        for semente in range(a.n):
            r = random.Random(semente)
            args, stdout, stderr, codigo = casos(r)
            falso(dirb, stdout, stderr, codigo)
            p = subprocess.run([RTK, "gh", *args], cwd=trab, env=env, capture_output=True, timeout=60)
            esperado = (p.stdout, _limpa(p.stderr), p.returncode)
            amb = Ambiente.em_memoria(str(trab), env=env)
            cod = gh.rodar(args, amb)
            o, e = amb.saida_gravada()
            obtido = (o, e, cod)
            if esperado == obtido:
                ok += 1
                if a.v:
                    print(f"ok   {semente}: gh {' '.join(args)}")
                continue
            falhas.append(semente)
            print(f"DIFF semente {semente}: gh {' '.join(args)}  (codigo {codigo})")
            for rotulo, x, y in (("stdout", esperado[0], obtido[0]), ("stderr", esperado[1], obtido[1]),
                                  ("codigo", esperado[2], obtido[2])):
                if x != y:
                    print(f"   {rotulo} rtk : {repr(x)[:500]}\n   {rotulo} porte: {repr(y)[:500]}")
    print(f"{ok}/{a.n} identicos, {len(falhas)} diferentes")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
