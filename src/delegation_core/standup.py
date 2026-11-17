"""Standup: o que aconteceu nas ultimas horas, de todas as fontes, numa chamada.

Equivale ao agente de "briefs" do Paperclip, sem modelo: so juntar fatos que
ja existem, para o agente nao fazer seis chamadas e montar ele mesmo.

Fontes: notas criadas e modificadas no vault, processos tocados, o vigia de
processos, aprovacoes e propostas pendentes, e o uso por ferramenta do
livro-caixa. `project` filtra notas e processos por um texto no caminho ou no
nome, sem caixa.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from pathlib import Path


def notas_recentes(cfg, desde: float, filtro: str = "", limite: int = 40) -> dict:
    raiz = Path(cfg.vault)
    criadas, mudadas = [], []
    for pasta in getattr(cfg, "vault_folders", []) or []:
        base = raiz / pasta
        if not base.is_dir():
            continue
        for dirpath, dirnames, arquivos in os.walk(base):
            dirnames[:] = [x for x in dirnames if not x.startswith(".")]
            for a in arquivos:
                if not a.endswith(".md"):
                    continue
                p = Path(dirpath) / a
                rel = str(p.relative_to(raiz))
                if filtro and filtro.lower() not in rel.lower():
                    continue
                st = p.stat()
                if st.st_mtime < desde:
                    continue
                nascida = getattr(st, "st_birthtime", None)
                hoje = datetime.fromtimestamp(desde).strftime("%Y-%m-%d")
                nova = (nascida is not None and nascida >= desde) or a[:10] >= hoje
                (criadas if nova else mudadas).append((st.st_mtime, rel))
    ordem = lambda xs: [r for _, r in sorted(xs, reverse=True)[:limite]]  # noqa: E731
    return {"created": ordem(criadas), "modified": ordem(mudadas),
            "created_count": len(criadas), "modified_count": len(mudadas)}


def montar(cfg, tracker, horas: float = 24, projeto: str = "") -> dict:
    desde = time.time() - horas * 3600
    corte = (datetime.now() - timedelta(hours=horas)).isoformat(timespec="seconds")
    saida = {"since": corte, "project": projeto, "notes": notas_recentes(cfg, desde, projeto)}

    if tracker is not None:
        tocados = [p for p in tracker.list_processes(status="all") if p["updated"] >= corte]
        if projeto:
            tocados = [p for p in tocados if projeto.lower() in (p["name"] + " " + p["description"]).lower()]
        saida["processes"] = [{
            "id": p["id"], "name": p["name"], "status": p["status"], "owner": p.get("owner"),
            "steps_done": f"{sum(s['done'] for s in p['steps'])}/{len(p['steps'])}" if p["steps"] else "open",
            "new_notes": [n["text"] for n in p["notes"] if n["timestamp"] >= corte][-3:],
        } for p in tocados]
        w = tracker.watchdog()
        saida["attention"] = {k: len(v) for k, v in w.items() if k != "count" and v}

    from . import config
    try:
        from .governanca import Aprovacoes
        saida["pending_approvals"] = len(Aprovacoes(config.CONFIG_DIR / "approvals.json").listar("pending"))
    except Exception:  # noqa: BLE001
        pass
    try:
        from .perguntas import listar
        abertas = listar("open", projeto)
        saida["open_questions"] = {"count": len(abertas),
                                   "high": [q["question"] for q in abertas if q["severity"] == "high"][:5]}
    except Exception:  # noqa: BLE001
        pass
    try:
        from .memoria import propostas
        saida["pending_proposals"] = len(propostas().listar("pending"))
    except Exception:  # noqa: BLE001
        pass
    try:
        from . import livro_mcp
        lv = livro_mcp.livro(cfg)
        if lv is not None:
            rel = lv.relatorio(desde=desde)
            saida["usage"] = {"calls": rel["chamadas"], "clients": rel["clientes"],
                              "top_tools": [{"tool": f["ferramenta"], "calls": f["chamadas"], "errors": f["erros"]}
                                            for f in rel["ferramentas"][:5]]}
    except Exception:  # noqa: BLE001
        pass
    return saida
