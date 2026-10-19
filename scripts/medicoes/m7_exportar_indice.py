import os, chromadb, json, numpy as np, sys, time
S=os.environ.get("EXPORT_DIR","/tmp/m7")
c=chromadb.PersistentClient(path=f"{S}/chroma-copia", settings=chromadb.Settings(anonymized_telemetry=False))
cols=c.list_collections(); print([ (x.name) for x in cols])
col=c.get_collection("vault_bge_m3")
n=col.count(); print("count",n)
ids=[];docs=[];metas=[];vecs=[]
t=time.time(); off=0
while off<n:
    r=col.get(limit=2000,offset=off,include=["documents","metadatas","embeddings"])
    ids+=r["ids"];docs+=r["documents"];metas+=r["metadatas"];vecs.append(np.asarray(r["embeddings"],dtype=np.float32)); off+=len(r["ids"])
    if not r["ids"]: break
V=np.vstack(vecs); print(V.shape, time.time()-t)
np.save(f"{S}/export-vetores.npy",V)
with open(f"{S}/export-linhas.jsonl","w",encoding="utf-8") as f:
    for i,d,m in zip(ids,docs,metas): f.write(json.dumps({"id":i,"documento":d,"metadados":m},ensure_ascii=False)+"\n")
print("ok",len(ids))
