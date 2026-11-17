"""Confere, num daemon vivo, cada capacidade do enriquecimento de 27/09. So leitura.

Para rodar depois do merge na producao, ou em qualquer daemon:

    DC_URL=http://127.0.0.1:8787/mcp DC_CFG=~/.delegation_core/config.json \
        python scripts/conferir_enriquecimento.py

Cada linha diz OK, FALHA ou AUSENTE (ferramenta nao existe nesse daemon) e o
que foi visto. Nao escreve nada: nenhuma ferramenta de escrita e chamada.
`ask_vault` e `compress` usam o modelo local (~10 s cada).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client

URL = os.environ.get("DC_URL", "http://127.0.0.1:8787/mcp")
CFG = os.path.expanduser(os.environ.get("DC_CFG", "~/.delegation_core/config.json"))


def _json(txt: str):
    try:
        d = json.loads(txt)
    except ValueError:
        return txt
    if isinstance(d, dict) and set(d) == {"result"} and isinstance(d["result"], str):
        try:
            return json.loads(d["result"])
        except ValueError:
            return d["result"]
    return d


CHECAGENS = [
    # (ferramenta, argumentos, funcao que diz se a resposta e a esperada, o que mostrar)
    ("heartbeat", {}, lambda r: isinstance(r, dict) and "attention" in r and "hybrid_search" in r,
     lambda r: f"attention={'sim' if r.get('attention') is not None else 'sem arquivo'}, "
               f"busca={(r.get('hybrid_search') or {}).get('modo', r.get('hybrid_search'))}"),
    ("search_vault", {"query": "qual a porta do llama", "scope": "notes"},
     lambda r: isinstance(r, dict) and r.get("sources"),
     lambda r: f"{len(r['sources'])} fontes, facts={len(r.get('facts') or [])}, "
               f"retrieval={(r.get('quality') or {}).get('retrieval')}"),
    ("vault_facts", {"query": "port"}, lambda r: isinstance(r, dict) and "stats" in r,
     lambda r: f"{r['stats']}"),
    ("vault_dead_refs", {"limit": 1}, lambda r: isinstance(r, dict) and "paths_dead" in r,
     lambda r: f"{r['paths_dead']} mortos em {r['notes_with_dead']} notas"),
    ("dream_findings", {}, lambda r: isinstance(r, dict) and "findings" in r,
     lambda r: f"{len(r['findings'])} achados"),
    ("graph_stats", {"name": "delegation-core"}, lambda r: isinstance(r, dict) and "error" not in r,
     lambda r: f"{r.get('nos')} nos, {r.get('arestas')} arestas"),
    ("graph_notes", {"name": "delegation-core", "term": "search_vault"},
     lambda r: isinstance(r, dict) and "nodes_with_notes" in r,
     lambda r: f"{sum(len(n['notes']) for n in r['nodes_with_notes'])} notas citam search_vault"),
    ("graph_changed_notes", {"name": "delegation-core"}, lambda r: isinstance(r, dict) and "notes_total" in r,
     lambda r: f"{r['commits']} commits desde o build, {r['notes_total']} notas a conferir"),
    ("schedule_list", {}, lambda r: isinstance(r, (dict, list)) and "fatos-noturno" in json.dumps(r),
     lambda r: "agenda com fatos-noturno"),
    ("alerts", {}, lambda r: isinstance(r, dict) and "error" not in r,
     lambda r: f"{len(r.get('open') or r.get('abertos') or [])} abertos"),
    ("compress", {"source": "conferencia", "use_local": True,
                  "raw_content": "Na reuniao decidimos migrar o banco para o servidor novo em outubro. " * 12},
     lambda r: isinstance(r, dict) and r.get("compressed"),
     lambda r: f"{(r.get('quality') or {}).get('output_chars')} caracteres"),
    ("ask_vault", {"question": "Qual modelo local roda no llama-server?"},
     lambda r: isinstance(r, dict) and "found" in r and "error" not in r,
     lambda r: f"found={r['found']}, {len(r.get('claims') or [])} afirmacoes, {r.get('seconds')} s"),
]


async def main() -> int:
    token = json.load(open(CFG))["server_token"]
    falhas = 0
    async with create_mcp_http_client(headers={"Authorization": f"Bearer {token}"}) as hc, \
            streamable_http_client(URL, http_client=hc) as st:
        async with ClientSession(st[0], st[1]) as s:
            await s.initialize()
            existentes = {t.name for t in (await s.list_tools()).tools}
            for nome, args, ok, mostra in CHECAGENS:
                if nome not in existentes:
                    print(f"AUSENTE  {nome}")
                    falhas += 1
                    continue
                t0 = time.time()
                try:
                    r = _json((await s.call_tool(nome, args)).content[0].text)
                    passou = bool(ok(r))
                    detalhe = mostra(r) if passou else str(r)[:200]
                except Exception as e:  # noqa: BLE001
                    passou, detalhe = False, f"excecao: {e}"
                falhas += not passou
                print(f"{'OK    ' if passou else 'FALHA '}  {nome:20} {time.time() - t0:5.1f}s  {detalhe}")
    print(f"\n{len(CHECAGENS) - falhas} de {len(CHECAGENS)} conferidas")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
