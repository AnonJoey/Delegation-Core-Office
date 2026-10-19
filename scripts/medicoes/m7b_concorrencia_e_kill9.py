"""Escritores concorrentes + leitor + kill -9. Uso: bench2.py <backend> <duracao_s>"""
import sys, os, time, json, random, signal, subprocess, shutil, sqlite3
import numpy as np
S=os.environ.get("BENCH_DIR","/tmp/m7-bench")
B=int(os.environ.get("LOTE","50")); D=1024

_CL={}
def _chroma():
    if "c" not in _CL:
        import chromadb
        _CL["c"]=chromadb.PersistentClient(path=f"{S}/chroma-c",settings=chromadb.Settings(anonymized_telemetry=False)).get_collection("vault_bge_m3")
    return _CL["c"]
def abrir(backend, ro=False):
    if backend=="chroma": return _chroma()
    if backend in ("np","vec"):
        c=sqlite3.connect(f"{S}/{backend}-c.db", timeout=60); c.execute("pragma busy_timeout=60000"); c.execute("pragma journal_mode=wal"); c.execute("pragma synchronous=normal")
        if backend=="vec":
            import sqlite_vec; c.enable_load_extension(True); sqlite_vec.load(c)
        return c
    import lancedb; return lancedb.connect(f"{S}/lance-c").open_table("v")

def escrever(backend, wid, lote):
    rng=np.random.default_rng(abs(hash((wid,lote)))%2**32)
    v=rng.normal(size=(B,D)).astype(np.float32); v/=np.linalg.norm(v,axis=1,keepdims=True)
    ids=[f"w{wid}-{lote}-{i}" for i in range(B)]
    if backend=="np":
        c=abrir(backend); c.execute("begin immediate")
        c.executemany("insert or replace into chunks(id,doc,meta,kind,ext,vec) values(?,?,?,?,?,?)",[(ids[i],"x","{}","note","false",v[i].tobytes()) for i in range(B)]); c.commit(); c.close()
    elif backend=="vec":
        c=abrir(backend); c.execute("begin immediate")
        for i in range(B):
            c.execute("delete from v where id=?",(ids[i],)); c.execute("insert into v(id,embedding,kind,ext) values(?,?,?,?)",(ids[i],v[i].tobytes(),"note","false"))
        c.commit(); c.close()
    elif backend=="chroma":
        _chroma().upsert(ids=ids,embeddings=[x.tolist() for x in v],metadatas=[{"kind":"note","is_external":"false"}]*B,documents=["x"]*B)
    else:
        import pyarrow as pa
        t=abrir(backend)
        dados=pa.table({"id":ids,"kind":["note"]*B,"ext":["false"]*B,"vector":pa.FixedSizeListArray.from_arrays(pa.array(v.ravel(),pa.float32()),D)})
        t.merge_insert("id").when_matched_update_all().when_not_matched_insert_all().execute(dados)

def papel_escritor(backend, wid):
    lote=0
    while True:
        try:
            escrever(backend,wid,lote)
        except Exception as e:
            with open(f"{S}/erros-{wid}.log","a") as f: f.write(f"{lote} {type(e).__name__}: {str(e)[:150]}\n")
            lote+=1; continue
        with open(f"{S}/ok-{wid}.log","a") as f: f.write(f"{lote}\n"); f.flush(); os.fsync(f.fileno())
        lote+=1; time.sleep(0.05)

def papel_leitor(backend, dur):
    rng=np.random.default_rng(1); t_fim=time.time()+dur; n=0; err=0; lat=[]; msgs=set()
    c=abrir(backend)
    while time.time()<t_fim:
        q=rng.normal(size=D).astype(np.float32); q/=np.linalg.norm(q)
        t0=time.perf_counter()
        try:
            if backend=="np":
                c.execute("select id from chunks limit 1").fetchone()
            elif backend=="vec":
                c.execute("select id from v where embedding match ? and k=10",(q.tobytes(),)).fetchall()
            elif backend=="chroma":
                c.query(query_embeddings=[q.tolist()],n_results=10)
            else:
                c.search(q).metric("cosine").limit(10).to_arrow()
            n+=1
        except Exception as e:
            err+=1; msgs.add(f"{type(e).__name__}: {str(e)[:100]}")
        lat.append((time.perf_counter()-t0)*1000); time.sleep(0.05)
    print(json.dumps({"leituras":n,"erros":err,"p50":float(np.median(lat)),"max":float(max(lat)),"msgs":sorted(msgs)[:3]}))

def prep(backend):
    for f in os.listdir(S):
        if f.startswith(("ok-","erros-")): os.remove(f"{S}/{f}")
    if backend=="chroma": return
    if backend=="np": base="np.db"; dst="np-c.db"
    elif backend=="vec": base="vec.db"; dst="vec-c.db"
    else: shutil.rmtree(f"{S}/lance-c",ignore_errors=True); shutil.copytree(f"{S}/lance",f"{S}/lance-c"); return
    for e in ("","-wal","-shm"):
        if os.path.exists(f"{S}/{dst}{e}"): os.remove(f"{S}/{dst}{e}")
    shutil.copy(f"{S}/{base}",f"{S}/{dst}")
    # o base foi fechado sem checkpoint? copiar -wal se existir
    for e in ("-wal","-shm"):
        if os.path.exists(f"{S}/{base}{e}"): shutil.copy(f"{S}/{base}{e}",f"{S}/{dst}{e}")

def verificar(backend):
    ok={}; 
    for w in range(4):
        p=f"{S}/ok-{w}.log"; ok[w]={int(x) for x in open(p).read().split()} if os.path.exists(p) else set()
    res={"lotes_confirmados":sum(len(v) for v in ok.values())}
    try:
        if backend in ("np","vec"):
            c=abrir(backend); tbl="chunks" if backend=="np" else "v"
            res["integrity_check"]=c.execute("pragma integrity_check").fetchone()[0]
            rows=c.execute(f"select id from {tbl} where id like 'w%'").fetchall(); ids=[r[0] for r in rows]
            total=c.execute(f"select count(*) from {tbl}").fetchone()[0]
        else:
            t=abrir(backend); tab=t.to_arrow().select(["id"]); ids=[x for x in tab["id"].to_pylist() if x.startswith("w")]; total=t.count_rows()
        from collections import Counter
        por=Counter("-".join(i.split("-")[:2]) for i in ids)
        res["total_linhas"]=total; res["linhas_w"]=len(ids)
        res["lotes_meio_escritos"]=sum(1 for k,v in por.items() if v!=B)
        res["duplicados"]=len(ids)-len(set(ids))
        perdidos=[ (w,l) for w in ok for l in ok[w] if por.get(f"w{w}-{l}",0)!=B]
        res["lotes_confirmados_perdidos"]=len(perdidos)
        res["lotes_presentes"]=len(por)
    except Exception as e:
        res["ERRO_AO_VERIFICAR"]=f"{type(e).__name__}: {str(e)[:200]}"
    print(json.dumps(res))

if __name__=="__main__":
    modo=sys.argv[1]
    if modo=="escritor": papel_escritor(sys.argv[2],int(sys.argv[3])); sys.exit()
    if modo=="leitor": papel_leitor(sys.argv[2],float(sys.argv[3])); sys.exit()
    backend=modo; dur=float(sys.argv[2]); prep(backend)
    me=os.path.abspath(__file__); py=sys.executable
    esc={w:subprocess.Popen([py,me,"escritor",backend,str(w)]) for w in range(4)}
    lei=subprocess.Popen([py,me,"leitor",backend,str(dur)],stdout=subprocess.PIPE,text=True)
    t_fim=time.time()+dur; mortes=0; prox=time.time()+2.5; prox_id=100
    while time.time()<t_fim:
        time.sleep(0.2)
        if time.time()>=prox:
            w=random.choice(list(esc)); esc[w].send_signal(signal.SIGKILL); esc[w].wait(); mortes+=1
            nid=prox_id; prox_id+=1; del esc[w]; esc[nid]=subprocess.Popen([py,me,"escritor",backend,str(nid)])
            prox=time.time()+random.uniform(1.5,3.5)
    for p in esc.values(): p.send_signal(signal.SIGKILL); p.wait()
    out,_=lei.communicate(timeout=60); print("leitor:",out.strip()); print("kill -9:",mortes)
    # ids de escritores: os logs ok-<id>
    verificar(backend) if False else None
    ok={}
    for f in sorted(os.listdir(S)):
        if f.startswith("ok-"): ok[int(f[3:-4])]={int(x) for x in open(f"{S}/{f}").read().split()}
    # reaproveita verificar com todos os ids
    import types
    def _v():
        res={"lotes_confirmados":sum(len(v) for v in ok.values())}
        try:
            if backend in ("np","vec"):
                c=abrir(backend); tbl="chunks" if backend=="np" else "v"
                res["integrity_check"]=c.execute("pragma integrity_check").fetchone()[0]
                ids=[r[0] for r in c.execute(f"select id from {tbl} where id like 'w%'")]; total=c.execute(f"select count(*) from {tbl}").fetchone()[0]
            elif backend=="chroma":
                t=abrir(backend); g=t.get(include=[],limit=10**7); ids=[x for x in g["ids"] if x.startswith("w")]; total=t.count()
            else:
                t=abrir(backend); ids=[x for x in t.to_arrow().select(["id"])["id"].to_pylist() if x.startswith("w")]; total=t.count_rows()
            from collections import Counter
            por=Counter("-".join(i.split("-")[:2]) for i in ids)
            res.update(total_linhas=total,duplicados=len(ids)-len(set(ids)),lotes_presentes=len(por),
                       lotes_meio_escritos=sum(1 for v in por.values() if v!=B),
                       lotes_confirmados_perdidos=sum(1 for w in ok for l in ok[w] if por.get(f"w{w}-{l}",0)!=B))
        except Exception as e: res["ERRO_AO_VERIFICAR"]=f"{type(e).__name__}: {str(e)[:200]}"
        errs=sum(len(open(f"{S}/{f}").read().splitlines()) for f in os.listdir(S) if f.startswith("erros-"))
        res["lotes_com_erro_no_escritor"]=errs
        if errs:
            from collections import Counter as C
            res["tipos_de_erro"]=dict(C(l.split(" ",1)[1][:80] for f in os.listdir(S) if f.startswith("erros-") for l in open(f"{S}/{f}").read().splitlines()).most_common(3))
        print(json.dumps(res,ensure_ascii=False))
    _v()
