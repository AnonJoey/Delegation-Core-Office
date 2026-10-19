import os
import json, numpy as np, os
S=os.environ.get("EXPORT_DIR","/tmp/m7")
def carregar():
    V=np.load(f"{S}/export-vetores.npy")
    V/=np.linalg.norm(V,axis=1,keepdims=True)+1e-12
    ids=[];docs=[];metas=[]
    for l in open(f"{S}/export-linhas.jsonl",encoding="utf-8"):
        r=json.loads(l); ids.append(r["id"]); docs.append(r["documento"]); metas.append(r["metadados"])
    return ids,docs,metas,V
def chave(m):
    return (str(m.get("kind","")), str(m.get("is_external","")), str(m.get("folder","")), str(m.get("graph","")))
