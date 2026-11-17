"""Paridade do porte (filtros_saida) com o binario real do RTK.

Uso: RTK_BIN=/caminho/rtk python scripts/paridade_rtk.py <dir-temporario>
Para cada filtro, um comando falso imprime entradas que exercitam todos os
estagios; a saida do RTK real e a do porte sao comparadas. HOME temporario.
"""
import json, os, random, re, subprocess, sys, tomllib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from delegation_core.filtros_saida import motor, execucao
from delegation_core import config
config.CONFIG_DIR = Path(sys.argv[1]) / 'dc'
import re as _re
HX = _re.compile(r'recall [0-9a-f]{12}')
S = Path(sys.argv[1]); (S / "bin").mkdir(parents=True, exist_ok=True); (S / "home").mkdir(exist_ok=True); RTK = os.environ["RTK_BIN"]
filtros, testes = motor.carregar_embutidos()
rnd = random.Random(7)

def comando_para(f):
    cands = [f.nome.replace("-", " "), f.nome, f.nome.split("-")[0]]
    for c in cands:
        for extra in ("", " status", " run", " build", " plan", " list"):
            cmd = c + extra
            if f.match.search(cmd) and motor.achar(cmd, filtros) is f:
                return cmd
    return None

def entradas(f):
    base = [c["input"] for c in testes.get(f.nome, [])]
    corpo = "\n".join(base)
    ansi = "\n".join(f"\x1b[31m{l}\x1b[0m" for l in corpo.split("\n")[:20])
    longa = "x" * 450 + " fim"
    muitas = "\n".join(f"line {i} " + ("ok" if i % 3 else "") for i in range(260))
    misto = "\n".join(rnd.sample(corpo.split("\n") * 3 + muitas.split("\n")[:120], k=min(200, len(corpo.split("\n")) * 3 + 120)))
    return {"testes": corpo, "ansi": ansi, "longa": longa + "\n" + corpo, "muitas": muitas,
            "misto": misto, "vazia": "\n\n", "crlf": corpo.replace("\n", "\r\n")}

env = dict(os.environ, HOME=str(S / "home"), PATH=f"{S}/bin:" + os.environ["PATH"], RTK_TELEMETRY_DISABLED="1", NO_COLOR="")
res = {"comparados": 0, "iguais": 0, "diferentes": [], "sem_comando": [], "rtk_nao_filtrou": []}
for f in filtros:
    cmd = comando_para(f)
    if not cmd:
        res["sem_comando"].append(f.nome); continue
    exe = cmd.split()[0]
    for rot, txt in entradas(f).items():
        (S / "entrada.txt").write_bytes(txt.encode())
        b = S / "bin" / exe
        b.write_text(f"#!/bin/sh\ncat {S}/entrada.txt\n"); b.chmod(0o755)
        p = subprocess.run([RTK] + cmd.split(), env=env, capture_output=True, timeout=30)
        b.unlink()
        rtk_out = p.stdout.decode("utf-8", "replace").rstrip("\n")
        py_out = execucao.exibir(f, txt, cmd, 0, prefixo="rtk")["output"].rstrip("\n")
        res["comparados"] += 1
        if rtk_out == py_out or HX.sub('recall H', rtk_out) == HX.sub('recall H', py_out):
            res.setdefault('hash_igual', 0); res['hash_igual'] += rtk_out == py_out
            res["iguais"] += 1
        else:
            res["diferentes"].append({"filtro": f.nome, "cmd": cmd, "entrada": rot,
                                      "rtk": rtk_out, "py": py_out, "stderr": p.stderr.decode()[:200]})
json.dump(res, open(S / "resultado.json", "w"), indent=1, ensure_ascii=False)
print("comparados", res["comparados"], "iguais", res["iguais"], "diferentes", len(res["diferentes"]), "sem comando", len(res["sem_comando"]))
