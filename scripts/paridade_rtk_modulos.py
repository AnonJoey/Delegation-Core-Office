"""Paridade dos modulos do RTK portados (filtros_saida/modulos) com o binario real.

Uso: RTK_BIN=/caminho/rtk python scripts/paridade_rtk_modulos.py [MODULO ...] [-n N]

Para cada entrada sintetica, cria um executavel falso com o nome da ferramenta
(mypy, pytest...) que imprime a saida gravada e sai com o codigo dado; o RTK
roda esse falso e aplica o filtro dele. A saida do porte tem que ser igual.

O RTK agrupa varios resultados em HashMap, cuja ordem muda a cada processo.
Quando a saida do porte difere, o RTK roda mais 8 vezes: se o porte bate com
alguma delas, ou com a forma normalizada que ignora so a ordem de empate, a
diferenca e de ordem de empate e nao de logica.
"""

from __future__ import annotations

import argparse
import json
import importlib
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

from delegation_core.filtros_saida import modulos  # noqa: E402
from delegation_core.filtros_saida.modulos import base  # noqa: E402

RTK = os.environ.get("RTK_BIN", "rtk")


def rodar(comando: str, args: list[str], saida: str, codigo: int = 0, stderr: str = "",
          extras: dict[str, tuple[str, int]] | None = None) -> tuple[str, str, int]:
    with tempfile.TemporaryDirectory() as d:
        bindir = Path(d) / "bin"; bindir.mkdir()
        home = Path(d) / "home"; home.mkdir()
        falsos = {comando: (saida, codigo, stderr)}
        for nome, (s, c) in (extras or {}).items():
            falsos[nome] = (s, c, "")
        for nome, (s, c, e) in falsos.items():
            (bindir / f"{nome}.out").write_text(s, encoding="utf-8")
            (bindir / f"{nome}.err").write_text(e, encoding="utf-8")
            p = bindir / nome
            p.write_text(f'#!/bin/sh\ncat "{bindir}/{nome}.out"\ncat "{bindir}/{nome}.err" >&2\nexit {c}\n')
            p.chmod(p.stat().st_mode | stat.S_IEXEC)
        env = {"PATH": f"{bindir}:/usr/bin:/bin", "HOME": str(home), "NO_COLOR": "1",
               "RTK_NO_TRACK": "1", "XDG_DATA_HOME": str(home / ".local/share"),
               "XDG_CONFIG_HOME": str(home / ".config"), "LANG": "C.UTF-8"}
        r = subprocess.run([RTK, comando, *args], capture_output=True, text=True, env=env, cwd=d, timeout=60)
        return r.stdout, r.stderr, r.returncode


def _p(r): return "".join(r.choice(string.ascii_lowercase) for _ in range(r.randint(3, 9)))

def python_mypy(r):
    arqs = [f"src/{_p(r)}/{_p(r)}.py" for _ in range(r.randint(1, 6))]
    codes = ["arg-type", "return-value", "name-defined", "assignment", "attr-defined", "union-attr", "misc", ""]
    ls = []
    for _ in range(r.randint(0, 40)):
        a = r.choice(arqs); col = f":{r.randint(1,80)}" if r.random() < .4 else ""
        sev = r.choice(["error"] * 6 + ["warning", "note"])
        msg = " ".join(_p(r) for _ in range(r.randint(2, 30)))
        c = r.choice(codes)
        ls.append(f"{a}:{r.randint(1,999)}{col}: {sev}: {msg}" + (f"  [{c}]" if c else ""))
        if r.random() < .25:
            ls.append(f"{a}:{r.randint(1,999)}: note: {' '.join(_p(r) for _ in range(r.randint(2,12)))}")
    if r.random() < .15:
        ls.insert(0, "mypy: error: " + _p(r) + " is not a valid Python package name")
    if r.random() < .1:
        ls.append("\x1b[31merror\x1b[0m: something " + _p(r))
    n = sum(1 for l in ls if ": error:" in l)
    ls.append(f"Found {n} errors in {len(arqs)} files (checked {r.randint(5,90)} source files)" if n else "Success: no issues found in 12 source files")
    codigo = 1 if n else r.choice([0, 0, 2])
    return "\n".join(ls) + "\n", codigo, ["src"]


def empate_python_mypy(t):
    """Ordem e corte do top 5 de codigos dependem do HashMap do RTK em empate."""
    return tuple(sorted(l for l in t.split("\n") if not l.startswith("Top codes:")))


def python_pytest(r):
    arqs = [f"tests/test_{_p(r)}.py" for _ in range(r.randint(1, 5))]
    n = r.randint(0, 60)
    falhas = r.randint(0, min(n, 14)) if r.random() < .7 else 0
    pulados = r.randint(0, 3) if r.random() < .3 else 0
    xf = r.randint(0, 13) if r.random() < .2 else 0
    ls = []
    verboso = r.random() < .6
    if verboso:
        ls += ["=" * 20 + " test session starts " + "=" * 20, "platform linux -- Python 3.12.3, pytest-8.3.2",
               f"rootdir: /home/x/{_p(r)}", f"collected {n} items", ""]
        for a in arqs:
            ls.append(f"{a} " + "".join(r.choice(".....F.s") for _ in range(r.randint(1, 20))) + f"  [{r.randint(1,100):3d}%]")
    nomes = [f"{r.choice(arqs)}::test_{_p(r)}" for _ in range(falhas)]
    if falhas and verboso:
        ls += ["", "=" * 20 + " FAILURES " + "=" * 20]
        for nm in nomes:
            ls.append("_" * 10 + " " + nm.split("::")[1] + " " + "_" * 10)
            ls.append("")
            ls.append(f"    def {nm.split('::')[1]}():")
            ls.append(f">       assert {_p(r)}() == {r.randint(0, 9)}")
            ls.append(f"E       AssertionError: assert {r.randint(0, 9)} == {r.randint(0, 9)}")
            if r.random() < .5:
                ls.append(f"E        +  where {r.randint(0,9)} = {_p(r)}()")
            ls.append("")
            ls.append(f"{nm.split('::')[0]}:{r.randint(1, 300)}: AssertionError")
    if falhas or xf:
        ls.append("=" * 10 + " short test summary info " + "=" * 10)
        for nm in nomes:
            ls.append(f"FAILED {nm} - AssertionError: assert {r.randint(0,9)} == {r.randint(0,9)}")
        for _ in range(xf):
            ls.append(f"XFAIL {r.choice(arqs)}::test_{_p(r)} - motivo {_p(r)}")
    passados = max(0, n - falhas - pulados - xf)
    partes = []
    if falhas: partes.append(f"{falhas} failed")
    if passados: partes.append(f"{passados} passed")
    if pulados: partes.append(f"{pulados} skipped")
    if xf: partes.append(f"{xf} xfailed")
    tempo = f"{r.uniform(0, 30):.2f}s"
    if partes:
        txt = ", ".join(partes) + f" in {tempo}"
        ls.append(("=" * 10 + f" {txt} " + "=" * 10) if verboso or r.random() < .5 else txt)
    else:
        ls.append(f"no tests ran in {tempo}")
    codigo = 1 if falhas else (5 if not partes else 0)
    if r.random() < .05:
        codigo = 2
    return "\n".join(ls) + "\n", codigo, ["-x"]


def python_ruff(r):
    tipo = r.choice(["check", "check", "check", "format", "concise"])
    if tipo == "format":
        arqs = [f"src/{_p(r)}/{_p(r)}.py" for _ in range(r.randint(0, 14))]
        ls = [f"Would reformat: {a}" for a in arqs]
        ok = r.randint(0, 40)
        if arqs:
            ls.append(f"{len(arqs)} files would be reformatted" + (f", {ok} files left unchanged" if ok else ""))
        else:
            ls.append(f"{ok} files left unchanged")
        return "\n".join(ls) + "\n", 1 if arqs else 0, ["format", "--check"]
    if tipo == "concise":
        return "src/a.py:1:1: F401 [*] `os` imported but unused\nFound 1 error.\n", 1, ["check", "--output-format=concise"]
    arqs = [f"/home/x/proj/{r.choice(['src', 'lib', 'tests', 'app'])}/{_p(r)}.py" for _ in range(r.randint(1, 14))]
    codes = ["F401", "E501", "B008", "UP006", "I001", "F841", "E711", "SIM108", "RUF100"]
    diags = []
    for _ in range(r.randint(0, 70)):
        d = {"code": r.choice(codes), "message": " ".join(_p(r) for _ in range(r.randint(2, 25))),
             "location": {"row": r.randint(1, 900), "column": r.randint(1, 120)},
             "end_location": {"row": 1, "column": 2}, "filename": r.choice(arqs),
             "fix": {"applicability": "safe", "edits": []} if r.random() < .4 else None,
             "noqa_row": 1, "url": "https://docs.astral.sh/ruff/rules/x"}
        diags.append(d)
    return json.dumps(diags, indent=2) + "\n", 1 if diags else 0, ["check", "src"] if r.random() < .5 else []


def empate_python_ruff(t):
    """Em empate, o RTK escolhe outra regra ou arquivo para o top (HashMap). Os
    nomes nas linhas de contagem viram *; contagens, estrutura e a lista de
    violacoes (deterministica) continuam comparadas."""
    import re
    linhas = []
    for l in t.split("\n"):
        l = re.sub(r"^(\s+)\S+ \((\d+x?)\)$", r"\1* (\2)", l)
        l = re.sub(r"^  \S+ \((\d+) issues\)$", r"  * (\1 issues)", l)
        linhas.append(l)
    return tuple(sorted(linhas))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("modulos", nargs="*", help="ex.: python.mypy (padrao: todos os portados)")
    ap.add_argument("-n", type=int, default=200)
    a = ap.parse_args()
    alvos = a.modulos or list(modulos.PORTADOS.values())
    # As dicas de recuperacao com o nome do RTK: "delegation-core recall" tem 12
    # caracteres a mais e, em saida no limite, muda a decisao do never_worse.
    base.PREFIXO = "rtk"
    falhas = 0
    for nome in alvos:
        mod = importlib.import_module(f"delegation_core.filtros_saida.modulos.{nome}")
        chave = nome.replace(".", "_")
        gerar, norm = globals()[chave], globals().get("empate_" + chave)
        comando = mod.COMANDOS[0]
        ok = empate = 0
        for s in range(a.n):
            saida, codigo, args = gerar(random.Random(s))
            esperado = rodar(comando, args, saida, codigo)[0]
            meu = modulos.mostrar(mod, saida, codigo, args, True) + "\n"
            if meu == esperado:
                ok += 1
                continue
            outras = {esperado} | {rodar(comando, args, saida, codigo)[0]
                                   for _ in range(8)}
            if meu in outras or (norm and len(outras) > 1 and norm(meu) in {norm(o) for o in outras}):
                empate += 1
            else:
                falhas += 1
                print(f"  {nome} semente {s}: diferente")
        print(f"{nome}: {ok}/{a.n} identicos, {empate} so na ordem de empate, {a.n - ok - empate} diferentes")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
