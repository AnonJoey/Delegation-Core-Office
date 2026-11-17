"""Chama as ferramentas de escrita num daemon de TESTE e marca assinatura de erro de Python.

So em ambiente isolado: confira antes com readlink -f que vault e config dir
nao caem na producao. Uso igual ao de varrer_ferramentas.py, mais a pasta de rascunho.
"""
import asyncio, json, sys, re, time
sys.path.insert(0, sys.argv[1])
from lt2 import call
S = sys.argv[2]
SINAIS = re.compile(r"is not defined|has no attribute|unexpected keyword|missing \d+ required|object is not|Traceback|NoneType")
PASSOS = [
 ("write_note", {"folder": "Scratch", "title": "Varredura de escrita 27-09", "content": "## Summary\nNota de teste da varredura. Porta `8181`."}),
 ("vault_update_note", {"note_name": "Varredura de escrita 27-09", "append_content": "Linha anexada."}),
 ("vault_rename_note", {"path": "Scratch/{p}", "new_title": "Varredura de escrita renomeada 27-09"}),
 ("vault_note_history", {"note": "Varredura de escrita renomeada 27-09"}),
 ("vault_note_restore", {"note": "Varredura de escrita renomeada 27-09", "version": 2}),
 ("process_create", {"name": "Teste da varredura", "steps": "a, b"}),
 ("process_update", {"process_id": "{proc}", "step_done": 0, "note": "ok"}),
 ("alerts_check", {}),
 ("schedule_run", {"name": "boletim-diario"}),
 ("dream_dismiss", {"old": "x.md", "new": "y.md"}),
 ("dream_apply", {"old": "x.md", "new": "y.md"}),
 ("ingest_folder", {"source_path": S + "/ingestir"}),
 ("ingest_forget", {"source_path": S + "/ingestir"}),
 ("export_session", {"title": "Varredura de escrita 27-09 sessao", "summary": "Teste da varredura de escrita no ambiente do fork."}),
 ("digest_transcripts", {"maximum": 1}),
 ("aferir_busca", {"amostras": 5}),
]
async def main():
    ctx = {}
    for t, a in PASSOS:
        a = {k: (v.format(**ctx) if isinstance(v, str) and "{" in v and ctx else v) for k, v in a.items()}
        t0 = time.time()
        try:
            r = await call(t, **a); txt = json.dumps(r, ensure_ascii=False) if not isinstance(r, str) else r
        except Exception as e:
            r, txt = None, f"EXCECAO {e}"
        if t == "write_note" and isinstance(r, dict): ctx["p"] = r.get("path", "").split("/")[-1]
        if t == "process_create" and isinstance(r, dict): ctx["proc"] = r.get("id", "")
        flag = "SUSPEITO" if SINAIS.search(txt) else ("erro" if '"error' in txt[:200] or "EXCECAO" in txt else "ok")
        print(f"{t:20} {flag:9} {time.time()-t0:5.1f}s {txt[:170]}", flush=True)
asyncio.run(main())
