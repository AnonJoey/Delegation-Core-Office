"""O que precisa de atencao, num arquivo que o hook de inicio de sessao le sem importar nada.

## Por que existe

Esta noite nasceram sinais que so aparecem para quem pergunta: alerta aberto
(`alerts`), nota que o sonho viu ser superada (`dream_findings`), fato em que
as notas divergem (`vault_facts(divergent=True)`), caminho citado que sumiu
(`vault_dead_refs`), codigo citado que saiu do grafo (`vault_note_code`). Nenhum agente pergunta por isso ao abrir uma sessao. O
hook `session_start_brief.py` ja injeta um resumo no contexto de toda sessao
do Claude Code, mas e stdlib pura e nao pode abrir sqlite do daemon nem
importar o pacote.

A ponte e um arquivo: o daemon grava `atencao.json` a cada rodada de alertas
(10 min) e o hook so le JSON. Cada item tem uma `chave` estavel; o hook mostra
o item uma vez e guarda a chave como vista.

## Criterio de lego

Cada fonte e opcional e falha sozinha: sem sonho, sem fatos ou sem alerta, a
secao some e o resto sai. Quem le nao precisa saber de onde veio.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

ARQUIVO = "atencao.json"


def _alertas(abertos: list[dict]) -> list[dict]:
    saida = []
    for a in abertos:
        # o inicio entra na chave: alerta que fechou e reabriu e aviso novo
        saida.append({"chave": f"alerta:{a.get('regra')}|{a.get('sujeito')}|{int(a.get('desde') or 0)}",
                      "tipo": "alert",
                      "texto": f"[{a.get('severidade', '?')}] {a.get('regra')}: {a.get('mensagem', '')}",
                      "dica": "alerts()"})
    return saida


def _achados(cfg) -> list[dict]:
    from . import sonho_vault

    reg = sonho_vault.achados(cfg)
    if reg is None:
        return []
    saida = []
    for f in reg.todos()[:10]:
        novo = (f.get("new_says") or "")[:140]
        saida.append({"chave": f"achado:{f['old']}>{f['new']}", "tipo": "superseded",
                      "texto": f"`{f['old']}` was {f['relation']} by `{f['new']}`" + (f": \"{novo}\"" if novo else ""),
                      "dica": "dream_findings() / dream_dismiss()", "old": f["old"], "new": f["new"]})
    return saida


def _divergencias(cfg) -> list[dict]:
    from . import fatos_vault

    arm = fatos_vault.armazem(cfg)
    if arm is None:
        return []
    saida = []
    for g in arm.divergencias(10):
        a, b = g["conflict"]
        saida.append({"chave": f"fato:{g['subject'].lower()}|{g['attribute']}|{a['value']}|{b['value']}",
                      "tipo": "divergent_fact",
                      "texto": f"{g['subject']} / {g['attribute']}: `{a['value']}` ({a['note']}, {a['date']}) "
                               f"vs `{b['value']}` ({b['note']}, {b['date']})",
                      "dica": "vault_facts(divergent=True)"})
    return saida


def _mortos(cfg) -> list[dict]:
    from . import referencias_vault

    if not referencias_vault.ligado(cfg):
        return []
    r = referencias_vault.varrer(cfg, limite=0, localizar=None)
    n = r.get("paths_dead", 0)
    if not n:
        return []
    return [{"chave": f"mortos:{n}", "tipo": "dead_paths",
             "texto": f"{n} paths cited in {r.get('notes_with_dead', 0)} live notes no longer exist on this machine",
             "dica": "vault_dead_refs()"}]


def _codigo_sumido(cfg) -> list[dict]:
    from . import codigo_vault

    if not codigo_vault.ligado(cfg):
        return []
    saida = []
    for n in codigo_vault.notas_com_sumido(cfg)[:10]:
        nomes = ", ".join(f"`{g['cited']}`" for g in n["gone"][:4])
        saida.append({"chave": f"sumido:{n['note']}|" + ",".join(sorted(g["cited"] for g in n["gone"])),
                      "tipo": "code_gone",
                      "texto": f"`{n['note']}` cites code removed from graph {n['gone'][0]['graph']}: {nomes}",
                      "dica": "vault_note_code()"})
    return saida


def _lacunas(cfg, agora: float | None = None) -> list[dict]:
    """Pergunta feita 2+ vezes na semana sem nenhuma resposta boa: nota que falta escrever."""
    from . import sonho_vault

    reg = sonho_vault.registro(cfg)
    if reg is None:
        return []
    desde = (agora or time.time()) - 7 * 86400
    saida = []
    for l in reg.lacunas(desde=desde)[:5]:
        saida.append({"chave": f"lacuna:{l['consulta'].strip().lower()}", "tipo": "knowledge_gap",
                      "texto": f"asked {l['vezes']}x this week with no good answer: \"{l['consulta'][:140]}\"",
                      "dica": "write_note() once it is answered"})
    return saida


_CACHE_MUDADO: dict = {}


def _codigo_mudado(cfg) -> list[dict]:
    """Por grafo de repositorio git, as 5 notas que mais citam codigo mudado desde o build.

    Guardado por (mtime do graph.json, HEAD do repositorio): a tarefa roda a
    cada 10 min e o diff so muda quando um dos dois muda.
    """
    import subprocess

    from .procs import sem_janela

    from . import codigo_vault
    from .graphbridge import _load_registry

    if not codigo_vault.ligado(cfg):
        return []
    saida = []
    for nome, gj in sorted(codigo_vault.grafos_em_disco(cfg).items()):
        fonte = ((_load_registry(cfg) or {}).get(nome) or {}).get("source_path")
        if not fonte or not Path(fonte).is_dir():
            continue
        head = subprocess.run(["git", "-C", fonte, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10, **sem_janela())
        if head.returncode != 0:
            continue
        marca = (gj.stat().st_mtime_ns, head.stdout.strip())
        if _CACHE_MUDADO.get(nome, (None,))[0] != marca:
            r = codigo_vault.notas_de_codigo_mudado(cfg, nome, limite=5)
            _CACHE_MUDADO[nome] = (marca, r)
        r = _CACHE_MUDADO[nome][1]
        for n in r.get("notes_to_review") or []:
            nomes = ", ".join(f"`{c['label']}`" for c in n["changed_code"][:4])
            saida.append({"chave": f"mudou:{nome}|{r.get('since_commit', '')[:12]}|{n['note']}", "tipo": "code_changed",
                          "texto": f"`{n['note']}` describes code changed since graph {nome} was built: {nomes}",
                          "dica": f"graph_changed_notes('{nome}')"})
    return saida


# Ordem de importancia: o hook e o heartbeat mostram 8 por sessao, entao o que
# vem primeiro e o que chega primeiro. Nota superada e codigo que sumiu dizem
# "isto esta errado"; codigo mudado e caminho morto dizem "confira".
FONTES = {"alertas": None, "achados": _achados, "codigo_sumido": _codigo_sumido,
          "divergencias": _divergencias, "codigo_mudado": _codigo_mudado, "lacunas": _lacunas,
          "mortos": _mortos}


def compor(cfg, abertos: list[dict] | None = None) -> dict:
    itens, erros = [], {}
    if abertos:
        itens += _alertas(abertos)
    for nome, fn in FONTES.items():
        if fn is None:
            continue
        try:
            itens += fn(cfg)
        except Exception as e:  # noqa: BLE001 - uma fonte quebrada nao cala as outras
            erros[nome] = str(e)[:200]
            logger.debug("atencao: fonte %s falhou: %s", nome, e)
    return {"gerado_em": time.time(), "itens": itens, "erros": erros}


def gravar(cfg, config_dir: Path, abertos: list[dict] | None = None) -> dict:
    d = compor(cfg, abertos)
    destino = Path(config_dir) / ARQUIVO
    tmp = destino.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, destino)
    return {"itens": len(d["itens"]), "erros": list(d["erros"])}


VISTAS = "atencao_vistas.json"
MAX_IDADE_S = 24 * 3600


def para_cliente(config_dir: Path, cliente: str, limite: int = 8, agora: float | None = None) -> dict | None:
    """Os itens que este cliente ainda nao viu, para o `heartbeat`.

    O hook de inicio de sessao so existe no Claude Code. Claude Desktop, Codex
    e os outros chamam `heartbeat()` ao abrir a sessao (o guia manda), entao o
    aviso vai por ali tambem, com o "ja visto" separado por nome de cliente.
    None quando nao ha arquivo ou ele esta velho (daemon sem a agenda).
    """
    base = Path(config_dir)
    try:
        d = json.loads((base / ARQUIVO).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (agora or time.time()) - float(d.get("gerado_em") or 0) > MAX_IDADE_S:
        return None
    try:
        vistas = json.loads((base / VISTAS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        vistas = {}
    ja = set(vistas.get(cliente) or [])
    itens = [i for i in d.get("itens") or [] if isinstance(i, dict) and i.get("chave")]
    novos = [i for i in itens if i["chave"] not in ja]
    mostrar = novos[:limite]
    if mostrar:
        vistas[cliente] = (list(vistas.get(cliente) or []) + [i["chave"] for i in mostrar])[-500:]
        tmp = base / (VISTAS + ".tmp")
        tmp.write_text(json.dumps(vistas, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, base / VISTAS)
    return {"new": [{"kind": i.get("tipo"), "what": i.get("texto"), "look_with": i.get("dica")} for i in mostrar],
            "not_shown_yet": len(novos) - len(mostrar), "total": len(itens)}
