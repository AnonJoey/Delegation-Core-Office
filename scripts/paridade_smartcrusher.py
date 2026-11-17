"""Paridade do SmartCrusher portado (compressao/smartcrusher) com o nucleo Rust do Headroom.

Uso (o _core compilado como em scripts/paridade_headroom.py):
  HEADROOM_CORE=/caminho/_core.abi3.so python scripts/paridade_smartcrusher.py [N]
  HEADROOM_CORE=... python scripts/paridade_smartcrusher.py --gravar

Sem argumento, roda N (padrao 1000) entradas sinteticas em oito configuracoes e
o walker de compactacao, e conta quantas saem identicas. `--gravar` regrava
tests/fixtures/smartcrusher/oraculo.json.gz com saidas do oraculo.
"""

from __future__ import annotations

import base64
import gzip
import importlib.util
import json
import os
import random
import string
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from delegation_core.compressao.smartcrusher import SmartCrusher, SmartCrusherConfig  # noqa: E402
from delegation_core.compressao.smartcrusher import compactacao as cp, jsonv  # noqa: E402

FIXTURE = RAIZ / "tests" / "fixtures" / "smartcrusher" / "oraculo.json.gz"
VARIANTES = {"padrao": ({}, True), "sem_compactacao": ({}, False), "lossless_only": ({"lossless_only": True}, True),
             "constantes": ({"factor_out_constants": True}, False), "sem_marcador": ({"enable_ccr_marker": False}, True),
             "max5": ({"max_items_after_crush": 5, "min_items_to_analyze": 3}, False),
             "markdown": ({}, "markdown-kv"), "json": ({}, "json")}


def _core():
    spec = importlib.util.spec_from_file_location("headroom._core", os.environ["HEADROOM_CORE"])
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _oraculo(core, kw, comp):
    oc = core.SmartCrusherConfig(**kw)
    if comp is True:
        return core.SmartCrusher(oc)
    if comp is False:
        return core.SmartCrusher.without_compaction(oc)
    return core.SmartCrusher.with_compaction_format(oc, comp)


# --- corpus sintetico --------------------------------------------------------
def palavra(r): return "".join(r.choice(string.ascii_lowercase) for _ in range(r.randint(3,9)))
def frase(r,n): return " ".join(palavra(r) for _ in range(n))

def item(r, i, forma):
    if forma == "log":
        return {"ts": f"2026-10-0{1+i//1000}T{(i//60)%24:02d}:{i%60:02d}:00Z", "level": r.choice(["INFO"]*8+["WARN","ERROR"]),
                "msg": frase(r, r.randint(3,10)), "line": i}
    if forma == "issue":
        d = {"number": 1000+i, "title": frase(r,5), "state": r.choice(["open","closed"]),
             "user": {"login": palavra(r), "id": r.randint(1,99999)}, "comments": r.randint(0,30),
             "labels": [palavra(r) for _ in range(r.randint(0,3))]}
        if r.random() < .2: d["body"] = frase(r, 60)
        return d
    if forma == "metric":
        return {"t": i, "cpu": round(r.gauss(40,5) + (60 if 30<i<35 else 0), 2), "mem": r.randint(1000,2000), "host": "h1"}
    if forma == "hetero":
        k = r.choice(["file","dir","link"])
        d = {"kind": k, "name": palavra(r)}
        if k=="file": d.update(size=r.randint(1,10**6), ext=r.choice(["py","md","rs"]))
        elif k=="dir": d.update(children=r.randint(0,40))
        else: d.update(target="/"+palavra(r), broken=r.random()<.1)
        return d
    if forma == "blob":
        return {"id": i, "name": palavra(r), "data": base64.b64encode(r.randbytes(r.choice([30,300]))).decode(),
                "html": "<div><p>" + frase(r, 50) + "</p><a href='x'>y</a></div>" if r.random()<.3 else None}
    if forma == "search":
        return {"path": f"src/{palavra(r)}/{palavra(r)}.py", "line": r.randint(1,900), "score": round(r.random(),4),
                "snippet": frase(r, r.randint(4,14)), "uuid": "%08x-%04x-4%03x-a%03x-%012x" % (r.getrandbits(32), r.getrandbits(16), r.getrandbits(12), r.getrandbits(12), r.getrandbits(48))}
    if forma == "borda":
        return {"id": i, "v": r.choice(["null", "", "a,b", 'diz "oi"', "linha\nnova", " espaco", "ação ü 日本", "x: y", 1, 1.0, -0, 1e3, None, True]),
                "nested": {"a": r.randint(0,3), "b": palavra(r)} if r.random()<.8 else None,
                "arr": [{"x": j, "y": palavra(r)} for j in range(r.randint(0,3))],
                "sj": json.dumps([{"q": j} for j in range(3)]) if r.random()<.3 else palavra(r)}
    return {"k": i}

def caso(seed):
    r = random.Random(seed)
    forma = r.choice(["log","issue","metric","hetero","blob","search","strs","nums","mixed","nested","dupes","small","borda","borda"])
    n = r.choice([3,5,8,9,12,20,30,50,80,150])
    if forma == "strs": doc = [frase(r, r.randint(1,8)) if r.random()>.1 else "ERROR: "+frase(r,4) for _ in range(n)]
    elif forma == "nums": doc = [round(r.gauss(100,10),r.choice([0,1,3])) if r.random()>.05 else 9999 for _ in range(n)]
    elif forma == "mixed": doc = [r.choice([palavra(r), r.randint(0,100), None, True, {"a": palavra(r)}, [1,2]]) for _ in range(n)]
    elif forma == "nested": doc = {"meta": {"total": n, "page": 1}, "data": {"items": [item(r,i,"issue") for i in range(n)]}, "q": json.dumps([item(r,i,"log") for i in range(n//2+2)])}
    elif forma == "dupes":
        base = [item(r,i,"log") for i in range(4)]; doc = [dict(r.choice(base)) for _ in range(n)]
    elif forma == "small": doc = {"ok": True, "n": n, "s": frase(r,3)}
    else: doc = [item(r,i,forma) for i in range(n)]
    indent = r.choice([None, None, 2])
    q = r.choice(["", "", "error", "closed issues", palavra(r)])
    bias = r.choice([1.0, 1.0, 0.7, 1.5])
    return json.dumps(doc, indent=indent, ensure_ascii=r.random()<.5), q, bias


def _het(total, n):
    out = []
    for i in range(total):
        k = "t%d" % (i % n)
        d = {"tipo": k, "id": i, "desc": "registro %d de %s com algum texto" % (i, k)}
        d["campo_" + k] = i * 7
        d["extra_" + k] = "v" * (5 + i % 4)
        out.append(d)
    return json.dumps(out)


def _borda():
    g = random.Random(7)
    b = [json.dumps([{"id": i, "v": ["null", "", None, "a,b", 'q"q', "l\nl"][i % 6], "w": "x" * 20} for i in range(40)]),
         json.dumps([{"id": i, "o": {"a": i, "b": "k"}, "s": json.dumps([{"z": 1}, {"z": 2}])} for i in range(30)]),
         json.dumps({"blob": "QUJD" * 100, "html": "<div><p>" + "a " * 200 + "</p><br/><i>x</i></div>", "txt": "palavra " * 60}),
         json.dumps([{"kind": ["a", "b", "c"][i % 3], "x" + str(i % 3): i, "y" + str(i % 3): "v"} for i in range(45)])]
    b += [json.dumps([{"id": i, "filhos": json.loads(_het(t, n))} for i in range(20)]) for t, n in ((10, 8), (9, 7), (11, 8))]
    b += [_het(10, 8), _het(9, 7), _het(8, 6), _het(30, 8), _het(20, 3)]
    b += [json.dumps({"img": base64.b64encode(g.randbytes(n)).decode()}) for n in (900, 3000)]
    b.append(json.dumps({"img": "QUJDREVGR0hJSktMTU5PUFFSU1RVVldY" * 50000}))
    b.append(json.dumps([{"id": i, "html": "<div><p>" + "palavra " * (150 + i * 40) + "</p><br/><i>x</i></div>"} for i in range(12)]))
    return b


def _walker_casos():
    w = random.Random(11)

    def hw():
        total = w.randint(2, 30)
        n = w.randint(1, 9)
        return [{"tipo": "t%d" % (i % n), "id": i,
                 **{f"t{i % n}_{j}": w.choice([1, "a", None, 2.5, {"q": 1}, "null", "a,b"]) for j in range(w.randint(0, 3))}}
                for i in range(total)]
    return [json.dumps(hw()) for _ in range(150)] + [json.dumps({"x": hw(), "y": [hw(), hw()]}) for _ in range(30)]


def gravar(core) -> int:
    casos = [x for x in (caso(s) for s in range(20000, 20200)) if len(x[0]) <= 15000][:110]
    casos += [(b, "", 1.0) for b in _borda()]
    saida = {"gerado_por": "headroom-core compilado do fonte", "variantes": {k: list(v) for k, v in VARIANTES.items()},
             "casos": [], "walker": []}
    for c, q, b in casos:
        reg = {"content": c, "query": q, "bias": b, "out": {}}
        for nome, (kw, comp) in VARIANTES.items():
            r = _oraculo(core, kw, comp).crush(c, q, b)
            reg["out"][nome] = [r.compressed, r.strategy, r.was_modified]
        saida["casos"].append(reg)
    o = core.SmartCrusher(core.SmartCrusherConfig())
    saida["walker"] = [[c, o.compact_document_json(c)] for c in _walker_casos()]
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(FIXTURE, "wt", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False)
    print(f"{len(casos)} casos e {len(saida['walker'])} do walker em {FIXTURE}")
    return 0


def main() -> int:
    core = _core()
    if "--gravar" in sys.argv:
        return gravar(core)
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    casos = [caso(s) for s in range(1000, 1000 + n)] + [(b, "", 1.0) for b in _borda()]
    falhas = 0
    for nome, (kw, comp) in VARIANTES.items():
        o, p = _oraculo(core, kw, comp), SmartCrusher(SmartCrusherConfig(**kw), compaction=comp)
        ok = 0
        for c, q, b in casos:
            a, m = o.crush(c, q, b), p.crush(c, q, b)
            ok += (a.compressed, a.strategy, a.was_modified) == (m.compressed, m.strategy, m.was_modified)
        falhas += len(casos) - ok
        print(f"{nome}: {ok}/{len(casos)} identicos")
    o = core.SmartCrusher(core.SmartCrusherConfig())
    wc = _walker_casos() + [c for c, _, _ in casos]
    ok = sum(o.compact_document_json(c) == jsonv.dumps(cp.DocumentCompactor().compact(jsonv.loads(c))) for c in wc)
    falhas += len(wc) - ok
    print(f"walker: {ok}/{len(wc)} identicos")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
