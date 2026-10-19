import sys, time, os, shutil, sqlite3, json, numpy as np
sys.path.insert(0,os.path.dirname(__file__))
from m7_comum import *
import sqlite_vec, lancedb, pyarrow as pa
ids,docs,metas,V=carregar(); N=len(ids)
print("N",N,"dim",V.shape[1])
rng=np.random.default_rng(7)
qi=rng.choice(N,300,replace=False)
Q=V[qi]+rng.normal(0,0.02,(300,V.shape[1])).astype(np.float32); Q/=np.linalg.norm(Q,axis=1,keepdims=True)
kind=np.array([str(m.get("kind","")) for m in metas]); ext=np.array([str(m.get("is_external","")) for m in metas])
filtros={"sem filtro":np.ones(N,bool),"kind != generated":kind!="generated","is_external = true":ext=="true","kind = note":kind=="note"}
print({k:int(v.sum()) for k,v in filtros.items()})
def exato(mask,k=10):
    idx=np.where(mask)[0]; sc=Q@V[idx].T
    return [set(idx[np.argsort(-s)[:k]]) for s in sc]
GT={n:exato(m) for n,m in filtros.items()}
pos={i:n for n,i in enumerate(ids)}
def avalia(nome,fn,build_s,tam):
    print(f"\n== {nome}: build {build_s:.1f}s, disco {tam/1e6:.0f} MB")
    for fnome,mask in filtros.items():
        t=[];rec=[]
        for j in range(100):
            t0=time.perf_counter(); r=fn(Q[j],10,fnome); t.append((time.perf_counter()-t0)*1000)
            rec.append(len(set(pos[x] for x in r)&GT[fnome][j])/10)
        print(f"  {fnome:20} p50={np.median(t):7.1f} ms  p95={np.percentile(t,95):7.1f} ms  recall@10 vs exato={np.mean(rec):.3f}")
def du(p):
    if os.path.isfile(p): return os.path.getsize(p)
    return sum(os.path.getsize(os.path.join(d,f)) for d,_,fs in os.walk(p) for f in fs)
# 1 SQLite + numpy
p=f"{S}/subst/np.db"; 
for e in ("","-wal","-shm"): 
    if os.path.exists(p+e): os.remove(p+e)
t0=time.perf_counter(); c=sqlite3.connect(p); c.execute("pragma journal_mode=wal"); c.execute("pragma synchronous=normal")
c.execute("create table chunks(id text primary key, doc text, meta text, kind text, ext text, vec blob)")
c.executemany("insert into chunks values(?,?,?,?,?,?)",[(ids[i],docs[i],json.dumps(metas[i],ensure_ascii=False),kind[i],ext[i],V[i].tobytes()) for i in range(N)]); c.commit()
mat=np.frombuffer(b"".join(r[0] for r in c.execute("select vec from chunks order by rowid")),dtype=np.float32).reshape(N,-1)
b=time.perf_counter()-t0
def q_np(v,k,f):
    m=filtros[f]; idx=np.where(m)[0]; s=mat[idx]@v; top=idx[np.argpartition(-s,k)[:k]]; top=top[np.argsort(-(mat[top]@v))]; return [ids[i] for i in top]
avalia("SQLite+numpy (exato)",q_np,b,du(p)); c.close()
# 2 sqlite-vec
p=f"{S}/subst/vec.db"
for e in ("","-wal","-shm"):
    if os.path.exists(p+e): os.remove(p+e)
t0=time.perf_counter(); c=sqlite3.connect(p); c.enable_load_extension(True); sqlite_vec.load(c); c.execute("pragma journal_mode=wal"); c.execute("pragma synchronous=normal")
try:
    c.execute("create virtual table v using vec0(id text primary key, embedding float[1024] distance_metric=cosine, kind text, ext text)")
    c.executemany("insert into v(id,embedding,kind,ext) values(?,?,?,?)",[(ids[i],V[i].tobytes(),kind[i],ext[i]) for i in range(N)]); c.commit()
    b=time.perf_counter()-t0
    def q_vec(v,k,f):
        w={"sem filtro":"","kind != generated":"and kind != 'generated'","is_external = true":"and ext = 'true'","kind = note":"and kind = 'note'"}[f]
        return [r[0] for r in c.execute(f"select id from v where embedding match ? and k=? {w}",(v.tobytes(),k))]
    avalia("sqlite-vec vec0",q_vec,b,du(p))
except Exception as e: print("sqlite-vec FALHOU:",repr(e))
c.close()
# 3 LanceDB
p=f"{S}/subst/lance"; shutil.rmtree(p,ignore_errors=True)
t0=time.perf_counter(); db=lancedb.connect(p)
tb=db.create_table("v",data=pa.table({"id":ids,"kind":kind.tolist(),"ext":ext.tolist(),"vector":pa.FixedSizeListArray.from_arrays(pa.array(V.ravel(),pa.float32()),1024)}))
b=time.perf_counter()-t0
def q_lance(v,k,f):
    w={"sem filtro":None,"kind != generated":"kind != 'generated'","is_external = true":"ext = 'true'","kind = note":"kind = 'note'"}[f]
    q=tb.search(v).metric("cosine").limit(k)
    if w: q=q.where(w,prefilter=True)
    return q.to_arrow()["id"].to_pylist()
avalia("LanceDB (sem indice ANN)",q_lance,b,du(p))
