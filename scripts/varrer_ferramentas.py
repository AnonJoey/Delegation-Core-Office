"""Chama toda ferramenta de leitura no daemon e marca resposta com assinatura de erro de Python.

Nasceu em 27/09: o compress local falhava com NameError desde 03/09 e o
except Exception devolvia isso como falha comum. Uso: DC_URL=... DC_CFG=...
python scripts/varrer_ferramentas.py <pasta com lt2.py>
"""
import asyncio, json, sys, re, time
sys.path.insert(0, sys.argv[1])
from lt2 import call
from delegation_core.escopos import LEITURA
ARGS = {
 "compress": {"source": "t", "raw_content": "Decidimos migrar o banco em outubro. " * 40, "use_local": True},
 "search_vault": {"query": "porta do llama"}, "search_web": None, "read_note": {"note_name": "drop-in"},
 "graph_query": {"name": "delegation-core", "question": "reindex"}, "graph_node": {"name": "delegation-core", "term": "detect_device"},
 "graph_path": {"name": "delegation-core", "source": "search_vault", "target": "VaultManager"},
 "graph_stats": {"name": "delegation-core"}, "graph_report": {"name": "delegation-core"}, "graph_preview": None,
 "graph_affected": {"name": "delegation-core", "query": "reindex"}, "graph_notes": {"name": "delegation-core", "term": "search_vault"},
 "graph_changed_notes": {"name": "delegation-core"}, "vault_note_code": {"note": "drop-in"},
 "vault_find_similar": {"note_name": "drop-in"}, "vault_list_notes": {"folder": "Fixes", "limit": 3},
 "vault_note_history": {"note": "drop-in"}, "vault_note_diff": {"note": "Digestao local das notas de setembro"},
 "vault_note_links": {"note_name": "drop-in"}, "vault_find_notes": {"query": "drop-in"},
 "process_get": {"process_id": "proc_1fa601"}, "task_status": {"job_id": "nada"}, "local_task_status": {"task_id": "nada"},
 "ask_vault": {"question": "Por que o BGE foi para a CPU?"}, "vault_facts": {"query": "port"},
 "vault_dead_refs": {"folder": "Fixes", "limit": 2}, "logs": {"lines": 5},
}
SINAIS = re.compile(r"is not defined|has no attribute|unexpected keyword|missing \d+ required|object is not|Traceback|NoneType")
async def main():
    for t in sorted(LEITURA):
        a = ARGS.get(t, {})
        if a is None: print(f"{t:22} pulado"); continue
        t0 = time.time()
        try:
            r = await call(t, **a)
            txt = json.dumps(r, ensure_ascii=False) if not isinstance(r, str) else r
        except Exception as e:
            txt = f"EXCECAO {e}"
        flag = "SUSPEITO" if SINAIS.search(txt) else ("erro" if '"error' in txt[:300] or "EXCECAO" in txt else "ok")
        print(f"{t:22} {flag:9} {time.time()-t0:5.1f}s {txt[:150] if flag != 'ok' else ''}", flush=True)
asyncio.run(main())
