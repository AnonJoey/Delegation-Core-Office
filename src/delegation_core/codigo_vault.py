"""Liga `ligacao_codigo/` ao vault e aos grafos construidos: nota -> codigo, e codigo -> notas.

- O indice de nomes vive em `<config>/codigo.sqlite3` e e sincronizado com
  os `graph.json` de `graphs_dir` antes de cada consulta (so recarrega grafo
  que mudou: o de 153 MB leva segundos, e nao se repete).
- Notas vivas: as mesmas pastas de decisao, correcao, procedimento, infra,
  projeto e ferramenta. Sessao e transcricao citam codigo de passagem.

Desligado com `codigo_enabled=false`.
"""

from __future__ import annotations

import threading
from pathlib import Path

from .ligacao_codigo import IndiceDeCodigo, ligar

PASTAS_PADRAO = ("Decisions", "Fixes", "Infrastructure", "Procedures", "Projects", "Tools")
_INDICE: dict[str, IndiceDeCodigo] = {}
_SYNC = threading.Lock()
_REVERSO: dict[str, tuple] = {}


def ligado(cfg) -> bool:
    return bool(getattr(cfg, "codigo_enabled", True))


def grafos_em_disco(cfg) -> dict[str, Path]:
    base = Path(getattr(cfg, "graphs_dir", "") or "")
    if not base.is_dir():
        return {}
    return {p.parent.name: p for p in base.glob("*/graph.json")}


def indice(cfg) -> IndiceDeCodigo | None:
    if not ligado(cfg):
        return None
    from .config import CONFIG_DIR

    caminho = str(Path(getattr(cfg, "codigo_path", "") or CONFIG_DIR / "codigo.sqlite3"))
    if caminho not in _INDICE:
        _INDICE[caminho] = IndiceDeCodigo(caminho)
    idx = _INDICE[caminho]
    with _SYNC:
        idx.sincronizar(grafos_em_disco(cfg))
    return idx


def _pastas(cfg) -> list[str]:
    return list(getattr(cfg, "codigo_pastas", None) or PASTAS_PADRAO)


def _notas(cfg):
    raiz = Path(cfg.vault)
    for pasta in _pastas(cfg):
        base = raiz / pasta
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*.md")):
            rel = p.relative_to(raiz)
            if any(x.startswith((".", "_")) for x in rel.parts):
                continue
            yield rel.as_posix(), p


def _formatar(r: dict) -> dict:
    return {"graph": r["graph"], "votes": r["votes"],
            "links": [{"cited": l["cited"], "targets": [a.como_dict() for a in l["targets"]]} for l in r["links"]]}


def sumidos_do_texto(idx, texto: str) -> list[dict]:
    """Citacoes da nota cujo nome sumiu de um grafo na ultima recarga dele."""
    from .ligacao_codigo import chave_da_citacao, citacoes

    saida = []
    for c in citacoes(texto):
        k = chave_da_citacao(c)
        # nome que volta ao grafo sai de `sumidos` na recarga (indice.py), entao
        # o que esta la nao existe mais naquele grafo
        for s in idx.sumido(k):
            saida.append({"cited": c, **s})
    return saida


def da_nota(cfg, caminho: str) -> dict:
    idx = indice(cfg)
    texto = (Path(cfg.vault) / caminho).read_text(encoding="utf-8", errors="ignore")
    r = {"note": caminho, **_formatar(ligar(texto, idx))}
    gone = sumidos_do_texto(idx, texto)
    if gone:
        r["gone"] = gone
    return r


def notas_com_sumido(cfg) -> list[dict]:
    """Notas vivas que citam funcao, classe ou arquivo que sumiu do codigo desde a carga anterior do grafo."""
    idx = indice(cfg)
    saida = []
    for rel, p in _notas(cfg):
        try:
            texto = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        g = sumidos_do_texto(idx, texto)
        if g:
            saida.append({"note": rel, "gone": g})
    return saida


def reverso(cfg) -> dict[tuple, list[str]]:
    """(grafo, id do no) e ("codigo", arquivo, rotulo, grafo) -> notas que o citam. Refeito quando nota ou grafo muda."""
    idx = indice(cfg)
    notas = list(_notas(cfg))
    marca = (tuple(idx.grafos()), tuple((rel, p.stat().st_mtime_ns) for rel, p in notas))
    chave = str(cfg.vault)
    if chave in _REVERSO and _REVERSO[chave][0] == marca:
        return _REVERSO[chave][1]
    mapa: dict[tuple, list[str]] = {}
    for rel, p in notas:
        try:
            texto = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for l in ligar(texto, idx)["links"]:
            for a in l["targets"]:
                # por no, e por identidade de codigo (arquivo + rotulo), que e
                # o que um repositorio e o fork dele tem em comum
                for k in ((a.grafo, a.id), ("codigo", a.arquivo, a.rotulo, a.grafo)):
                    mapa.setdefault(k, [])
                    if rel not in mapa[k]:
                        mapa[k].append(rel)
    _REVERSO[chave] = (marca, mapa)
    return mapa


def notas_do_termo(cfg, grafo: str, termo: str, limite: int = 20) -> dict:
    """Notas que citam os nos de `grafo` cujo nome e `termo` (funcao, classe ou arquivo)."""
    from .ligacao_codigo import chave_da_citacao

    idx = indice(cfg)
    alvos = [a for a in idx.buscar(chave_da_citacao(termo)) if a.grafo == grafo]
    mapa = reverso(cfg)
    saida = []
    for a in alvos:
        notas = list(mapa.get((a.grafo, a.id), []))
        via = {}
        # a nota que cita o fork (e por voto foi ligada ao grafo do fork) fala
        # da mesma funcao: entra, com o grafo por onde veio
        for k, ns in mapa.items():
            if k[0] == "codigo" and k[1] == a.arquivo and k[2] == a.rotulo and k[3] != a.grafo:
                for n in ns:
                    if n not in notas:
                        notas.append(n)
                        via[n] = k[3]
        if notas:
            d = {**a.como_dict(), "notes": notas[:limite]}
            if via:
                d["via_graph"] = {n: g for n, g in via.items() if n in d["notes"]}
            saida.append(d)
    return {"graph": grafo, "term": termo, "nodes_matched": len(alvos), "nodes_with_notes": saida}


def notas_de_codigo_mudado(cfg, grafo: str, anterior: bool = False, limite: int = 30) -> dict:
    """Notas vivas que citam funcao, classe ou arquivo mudado desde o build do grafo.

    `anterior=False`: do commit do `graph.json` ate o HEAD (o que o grafo ainda
    nao viu). `anterior=True`: do commit do `graph.anterior.json` ate o HEAD,
    que depois de um rebuild e "o que mudou desde o build de antes".
    """
    import json as _json
    import subprocess

    from .procs import sem_janela

    from . import registro_grafos
    from .ligacao_codigo import faixas_do_diff, nos_tocados

    base = Path(getattr(cfg, "graphs_dir", "")) / grafo
    arq = base / ("graph.anterior.json" if anterior else "graph.json")
    if not arq.is_file():
        return {"error": f"no {'previous ' if anterior else ''}graph file for '{grafo}'"}
    dados = _json.loads(arq.read_text(encoding="utf-8"))
    commit = dados.get("built_at_commit")
    fonte = ((registro_grafos._load_registry(cfg) or {}).get(grafo) or {}).get("source_path")
    if not commit or not fonte:
        return {"error": f"graph '{grafo}' has no built_at_commit or source_path; cannot diff"}
    r = subprocess.run(["git", "-C", fonte, "diff", "-U0", "--relative", f"{commit}..HEAD", "--", "."],
                       capture_output=True, text=True, timeout=60, **sem_janela())
    if r.returncode != 0:
        return {"error": f"git diff failed: {r.stderr.strip()[:200]}"}
    n_commits = subprocess.run(["git", "-C", fonte, "rev-list", "--count", f"{commit}..HEAD", "--", "."],
                               capture_output=True, text=True, timeout=30, **sem_janela()).stdout.strip()
    faixas = faixas_do_diff(r.stdout)
    tocados = nos_tocados(dados.get("nodes") or [], faixas)
    por_id = {n.get("id"): n for n in dados.get("nodes") or []}
    mapa = reverso(cfg)
    notas: dict[str, list[dict]] = {}
    for nid in tocados:
        no = por_id.get(nid) or {}
        citantes = set(mapa.get((grafo, nid), []))
        # identidade de codigo: a nota ligada ao grafo gemeo tambem fala dele
        for k, ns in mapa.items():
            if k[0] == "codigo" and k[1] == no.get("source_file") and k[2] == no.get("label"):
                citantes.update(ns)
        for rel in citantes:
            notas.setdefault(rel, []).append({"label": no.get("label"), "file": no.get("source_file"),
                                              "line": no.get("source_location")})
    lista = sorted(({"note": n, "changed_code": sorted(v, key=lambda x: x["label"] or "")}
                    for n, v in notas.items()), key=lambda d: (-len(d["changed_code"]), d["note"]))
    return {"graph": grafo, "since_commit": commit, "commits": int(n_commits or 0),
            "files_changed": len(faixas), "nodes_changed": len(tocados),
            "notes_to_review": lista[:limite], "notes_total": len(lista)}
