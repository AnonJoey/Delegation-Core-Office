"""Cenario 'longevo' do m6: A segura o indice aberto (o daemon); B (CLI/hook) abre, escreve 1200 linhas e sai. 10 ciclos."""
import sys, os, time, json, shutil, subprocess, sqlite3
import numpy as np
S=os.environ.get("BENCH_DIR","/tmp/m7-bench"); D=1024; LOTE=1200; CICLOS=10
def abrir(b):
    if b in ("np","vec"):
        c=sqlite3.connect(f"{S}/{b}-L.db",timeout=60); c.execute("pragma busy_timeout=60000"); c.execute("pragma journal_mode=wal"); c.execute("pragma synchronous=normal")
        if b=="vec":
            import sqlite_vec; c.enable_load_extension(True); sqlite_vec.load(c)
        return c
    import lancedb; return lancedb.connect(f"{S}/lance-L").open_table("v")
def conta(b,c):
    if b=="np": return c.execute("select count(*) from chunks").fetchone()[0]
    if b=="vec": return c.execute("select count(*) from v").fetchone()[0]
    return c.count_rows()
def escreve(b,ciclo):
    rng=np.random.default_rng(ciclo); v=rng.normal(size=(LOTE,D)).astype(np.float32); v/=np.linalg.norm(v,axis=1,keepdims=True)
    ids=[f"L{ciclo}-{i}" for i in range(LOTE)]; c=abrir(b)
    if b=="np":
        c.executemany("insert or replace into chunks(id,doc,meta,kind,ext,vec) values(?,?,?,?,?,?)",[(ids[i],"x","{}","note","false",v[i].tobytes()) for i in range(LOTE)]); c.commit()
    elif b=="vec":
        c.execute("begin immediate")
        for i in range(LOTE): c.execute("insert into v(id,embedding,kind,ext) values(?,?,?,?)",(ids[i],v[i].tobytes(),"note","false"))
        c.commit()
    else:
        import pyarrow as pa
        c.merge_insert("id").when_matched_update_all().when_not_matched_insert_all().execute(pa.table({"id":ids,"kind":["note"]*LOTE,"ext":["false"]*LOTE,"vector":pa.FixedSizeListArray.from_arrays(pa.array(v.ravel(),pa.float32()),D)}))
if __name__=="__main__":
    if sys.argv[1]=="B": escreve(sys.argv[2],int(sys.argv[3])); sys.exit()
    b=sys.argv[1]
    if b=="np": src,dst="np.db","np-L.db"
    elif b=="vec": src,dst="vec.db","vec-L.db"
    if b!="lance":
        for e in ("","-wal","-shm"):
            if os.path.exists(f"{S}/{dst}{e}"): os.remove(f"{S}/{dst}{e}")
        shutil.copy(f"{S}/{src}",f"{S}/{dst}")
    else:
        shutil.rmtree(f"{S}/lance-L",ignore_errors=True); shutil.copytree(f"{S}/lance",f"{S}/lance-L")
    a=abrir(b); base=conta(b,a); erros=[]; nao_viu=0
    for ciclo in range(CICLOS):
        p=subprocess.run([sys.executable,__file__,"B",b,str(ciclo)],capture_output=True,text=True)
        if p.returncode!=0: erros.append(f"B{ciclo} saiu {p.returncode}: {p.stderr.strip()[-80:]}")
        if conta(b,a)!=base+(ciclo+1)*LOTE: nao_viu+=1
    esperado=base+CICLOS*LOTE
    print(json.dumps({"backend":b,"base":base,"esperado":esperado,"contagem_final":conta(b,a),"erros_de_B":erros,"A_nao_viu_escrita":nao_viu},ensure_ascii=False))
