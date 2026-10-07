"""Migracao do indice do ChromaDB para o indice SQLite, sem perder dado.

O fluxo foi feito para que nenhuma etapa possa piorar a situacao de partida:

1. **Exportar** o Chroma num processo FILHO, com prazo. Abrir um indice do
   ChromaDB 1.5.x pode matar quem o abre (SIGSEGV) ou nunca voltar; num filho
   isso vira um codigo de saida, e o indice de origem so e lido, nunca escrito.
   O resultado e um formato neutro (linhas em JSONL e vetores em .npy) que
   fica guardado: se algo der errado depois, nao e preciso re-embedar 41 mil
   chunks para tentar de novo.
2. **Importar** para uma pasta temporaria ao lado do destino, nunca por cima.
3. **Verificar** o importado contra o exportado, linha a linha: contagem,
   ids na mesma ordem, texto, metadados e vetores identicos bit a bit, e a
   busca vizinha mais proxima contra a busca exata sobre a matriz exportada.
4. So se tudo bater a pasta temporaria vira o destino (renomeacao). O indice
   do Chroma nao e tocado em momento nenhum: voltar atras e voltar o
   `index_backend` para "chroma".

A fonte da verdade continua sendo os markdowns do vault; se o Chroma nem
abrir, `reindex --force` com `index_backend: sqlite` reconstroi o indice deles.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

logger = logging.getLogger("migracao_indice")

LOTE = 2000
PRAZO_DO_FILHO_SEG = 1800
VIZINHOS = 10


# ── exportacao (roda no filho) ───────────────────────────────────────────────

def exportar_chroma(chroma_dir: str, destino: str, amostra: int = 50) -> dict:
    """Le TODAS as colecoes do Chroma e grava o formato neutro em `destino`.

    Chamado dentro do processo filho. Escreve `export.json` por ultimo: sem ele
    a exportacao e tratada como incompleta.
    """
    import chromadb

    destino_p = Path(destino)
    destino_p.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(
        path=chroma_dir, settings=chromadb.Settings(anonymized_telemetry=False))
    resumo: dict = {"colecoes": {}, "chroma": getattr(chromadb, "__version__", "?")}
    for info in client.list_collections():
        col = client.get_collection(info.name)
        n = col.count()
        pasta = destino_p / info.name
        pasta.mkdir(exist_ok=True)
        vetores: list[np.ndarray] = []
        ids: list[str] = []
        with open(pasta / "linhas.jsonl", "w", encoding="utf-8") as f:
            desloc = 0
            while desloc < n:
                r = col.get(limit=LOTE, offset=desloc,
                            include=["documents", "metadatas", "embeddings"])
                if not r["ids"]:
                    break
                for i, d, m in zip(r["ids"], r["documents"], r["metadatas"]):
                    f.write(json.dumps({"id": i, "documento": d, "metadados": m},
                                       ensure_ascii=False) + "\n")
                ids += r["ids"]
                vetores.append(np.asarray(r["embeddings"], dtype=np.float32))
                desloc += len(r["ids"])
        matriz = np.vstack(vetores) if vetores else np.zeros((0, 0), dtype=np.float32)
        np.save(pasta / "vetores.npy", matriz)
        vizinhos: dict[str, list[str]] = {}
        if len(ids) and amostra:
            passo = max(len(ids) // amostra, 1)
            for p in range(0, len(ids), passo)[:amostra]:
                q = col.query(query_embeddings=[matriz[p].tolist()], n_results=VIZINHOS)
                vizinhos[str(p)] = q["ids"][0]
        (pasta / "vizinhos_chroma.json").write_text(json.dumps(vizinhos), encoding="utf-8")
        resumo["colecoes"][info.name] = {
            "linhas": len(ids), "contagem_declarada": n,
            "dim": int(matriz.shape[1]) if matriz.size else 0,
            "metadata": dict(info.metadata or {})}
    (destino_p / "export.json").write_text(json.dumps(resumo, indent=2), encoding="utf-8")
    return resumo


def _principal_do_filho(argv: list[str]) -> int:
    if len(argv) >= 3 and argv[0] == "exportar":
        r = exportar_chroma(argv[1], argv[2], int(argv[3]) if len(argv) > 3 else 50)
        print(json.dumps(r))
        return 0
    if len(argv) >= 4 and argv[0] == "consultar":
        return _consultar_filho(argv[1], argv[2], argv[3])
    sys.stderr.write("uso: migracao_indice exportar <chroma> <destino> [amostra]\n")
    return 2


def _consultar_filho(chroma_dir: str, entrada: str, saida: str) -> int:
    """Responde as consultas de `entrada` (JSON {colecao: matriz.npy}) no Chroma."""
    import chromadb

    client = chromadb.PersistentClient(
        path=chroma_dir, settings=chromadb.Settings(anonymized_telemetry=False))
    pedido = json.loads(Path(entrada).read_text(encoding="utf-8"))
    resposta: dict = {}
    for nome, arquivo in pedido.items():
        col = client.get_collection(nome)
        qs = np.load(arquivo)
        resposta[nome] = [col.query(query_embeddings=[q.tolist()], n_results=VIZINHOS)["ids"][0]
                          for q in qs]
    Path(saida).write_text(json.dumps(resposta), encoding="utf-8")
    return 0


def exportar_em_filho(chroma_dir: Path, destino: Path, amostra: int = 50,
                      prazo: float = PRAZO_DO_FILHO_SEG) -> dict:
    """Exporta num processo filho. Levanta RuntimeError com o motivo se falhar."""
    cmd = [sys.executable, "-m", "delegation_core.migracao_indice", "exportar",
           str(chroma_dir), str(destino), str(amostra)]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=prazo)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"o Chroma nao terminou de exportar em {int(prazo)} s "
                           "(o indice pode estar travado)") from None
    if p.returncode != 0:
        causa = (f"morto pelo sinal {-p.returncode}" if p.returncode < 0
                 else (p.stderr.strip().splitlines() or ["sem mensagem"])[-1])
        raise RuntimeError(f"o Chroma nao abriu para exportar ({causa}). Nada foi alterado. "
                           "Alternativa: index_backend=sqlite e `delegation-core reindex --force`, "
                           "que reconstroi o indice dos markdowns.")
    if not (destino / "export.json").exists():
        raise RuntimeError("exportacao incompleta (sem export.json)")
    return json.loads((destino / "export.json").read_text(encoding="utf-8"))


# ── importacao ───────────────────────────────────────────────────────────────

def importar(export_dir: Path, alvo_dir: Path) -> dict[str, int]:
    from .indice_sqlite import ClienteSqlite

    resumo = json.loads((export_dir / "export.json").read_text(encoding="utf-8"))
    cliente = ClienteSqlite(alvo_dir)
    contagens: dict[str, int] = {}
    try:
        for nome, info in resumo["colecoes"].items():
            col = cliente.get_or_create_collection(nome, metadata=info.get("metadata") or {})
            matriz = np.load(export_dir / nome / "vetores.npy", mmap_mode="r")
            lote_ids: list[str] = []
            lote_docs: list[str] = []
            lote_meta: list[dict] = []
            ini = 0

            def despejar():
                nonlocal lote_ids, lote_docs, lote_meta, ini
                if not lote_ids:
                    return
                col.upsert(ids=lote_ids, embeddings=np.asarray(matriz[ini:ini + len(lote_ids)]),
                           metadatas=lote_meta, documents=lote_docs)
                ini += len(lote_ids)
                lote_ids, lote_docs, lote_meta = [], [], []

            with open(export_dir / nome / "linhas.jsonl", encoding="utf-8") as f:
                for linha in f:
                    r = json.loads(linha)
                    lote_ids.append(r["id"])
                    lote_docs.append(r["documento"])
                    lote_meta.append(r["metadados"] or {})
                    if len(lote_ids) == LOTE:
                        despejar()
            despejar()
            contagens[nome] = col.count()
    finally:
        cliente.close()
    return contagens


# ── verificacao ──────────────────────────────────────────────────────────────

def verificar(export_dir: Path, alvo_dir: Path) -> dict:
    """Compara o indice SQLite com a exportacao. `ok` so e True se TUDO bate."""
    from .indice_sqlite import ClienteSqlite

    resumo = json.loads((export_dir / "export.json").read_text(encoding="utf-8"))
    cliente = ClienteSqlite(alvo_dir)
    relatorio: dict = {"colecoes": {}, "integridade_sqlite": cliente.verificar(), "ok": True}
    try:
        nomes_alvo = sorted(c.name for c in cliente.list_collections())
        if nomes_alvo != sorted(resumo["colecoes"]):
            relatorio["ok"] = False
            relatorio["colecoes_diferentes"] = {"origem": sorted(resumo["colecoes"]),
                                                "destino": nomes_alvo}
        if relatorio["integridade_sqlite"] != "ok":
            relatorio["ok"] = False
        for nome, info in resumo["colecoes"].items():
            col = cliente.get_collection(nome)
            r: dict = {"linhas_origem": info["linhas"], "linhas_destino": col.count(),
                       "problemas": []}
            if info["linhas"] != col.count():
                r["problemas"].append(f"contagem: {info['linhas']} na origem, {col.count()} no destino")
            matriz = np.load(export_dir / nome / "vetores.npy", mmap_mode="r")
            ini = 0
            diferentes = {"id": 0, "documento": 0, "metadados": 0, "vetor": 0}
            with open(export_dir / nome / "linhas.jsonl", encoding="utf-8") as f:
                while True:
                    lote = [json.loads(x) for _, x in zip(range(LOTE), f)]
                    if not lote:
                        break
                    got = col.get(limit=len(lote), offset=ini,
                                  include=["documents", "metadatas", "embeddings"])
                    if len(got["ids"]) != len(lote):
                        r["problemas"].append(f"faltam linhas a partir de {ini}")
                        break
                    esperado = np.asarray(matriz[ini:ini + len(lote)])
                    for k, linha in enumerate(lote):
                        if got["ids"][k] != linha["id"]:
                            diferentes["id"] += 1
                        if got["documents"][k] != linha["documento"]:
                            diferentes["documento"] += 1
                        if got["metadatas"][k] != (linha["metadados"] or {}):
                            diferentes["metadados"] += 1
                        if not np.array_equal(got["embeddings"][k], esperado[k]):
                            diferentes["vetor"] += 1
                    ini += len(lote)
            for campo, n in diferentes.items():
                if n:
                    r["problemas"].append(f"{n} linhas com {campo} diferente")
            # vizinhos: o SQLite contra a busca EXATA sobre a matriz exportada, e
            # contra o que o Chroma (aproximado) respondeu na hora da exportacao.
            vizinhos = json.loads((export_dir / nome / "vizinhos_chroma.json").read_text(encoding="utf-8"))
            if vizinhos and info["linhas"]:
                M = np.asarray(matriz)
                Mn = M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-12)
                ids = [json.loads(x)["id"] for x in open(export_dir / nome / "linhas.jsonl", encoding="utf-8")]
                exato_igual = 0
                sobreposicao = []
                for p, ids_chroma in vizinhos.items():
                    q = M[int(p)]
                    exato = [ids[i] for i in np.argsort(-(Mn @ (q / (np.linalg.norm(q) + 1e-12))))[:VIZINHOS]]
                    meu = col.query(query_embeddings=[q.tolist()], n_results=VIZINHOS)["ids"][0]
                    exato_igual += int(set(meu) == set(exato))
                    sobreposicao.append(len(set(meu) & set(ids_chroma)) / VIZINHOS)
                r["consultas"] = len(vizinhos)
                r["consultas_iguais_a_busca_exata"] = exato_igual
                r["sobreposicao_media_com_o_chroma"] = round(float(np.mean(sobreposicao)), 4)
                if exato_igual != len(vizinhos):
                    r["problemas"].append(
                        f"{len(vizinhos) - exato_igual} consultas diferem da busca exata")
            r["ok"] = not r["problemas"]
            relatorio["ok"] = relatorio["ok"] and r["ok"]
            relatorio["colecoes"][nome] = r
    finally:
        cliente.close()
    return relatorio


# ── orquestracao ─────────────────────────────────────────────────────────────

def migrar(cfg, *, origem: Path | None = None, destino: Path | None = None,
           amostra: int = 50, prazo: float = PRAZO_DO_FILHO_SEG, forcar: bool = False,
           pasta_de_trabalho: Path | None = None) -> dict:
    """Chroma -> SQLite. Devolve o relatorio; levanta RuntimeError se nao puder seguir."""
    from . import daemon

    origem = Path(origem or cfg.chroma_path)
    destino = Path(destino or cfg.sqlite_path)
    if not (origem / "chroma.sqlite3").exists():
        raise RuntimeError(f"nao ha indice do Chroma em {origem}")
    em_uso = origem.resolve() == Path(cfg.chroma_path).resolve()
    if em_uso and not forcar and daemon.is_listening(cfg):
        raise RuntimeError(
            "o daemon esta no ar e segura o indice do Chroma aberto. Abrir o mesmo "
            "indice por um segundo processo e exatamente o cenario que o corrompe. "
            "Pare o daemon (`delegation-core service stop`) ou aponte --from para uma copia.")
    marca = datetime.now().strftime("%Y%m%d-%H%M%S")
    trabalho = Path(pasta_de_trabalho or (Path.home() / ".delegation_core" / "migracao" / marca))
    export_dir = trabalho / "export"
    tmp = destino.parent / f"{destino.name}.novo-{marca}"
    if tmp.exists():
        shutil.rmtree(tmp)
    inicio = time.time()
    relatorio: dict = {"origem": str(origem), "destino": str(destino),
                       "exportacao": str(export_dir), "inicio": marca}
    try:
        relatorio["export"] = exportar_em_filho(origem, export_dir, amostra, prazo)
        relatorio["importado"] = importar(export_dir, tmp)
        relatorio["verificacao"] = verificar(export_dir, tmp)
        if not relatorio["verificacao"]["ok"]:
            raise RuntimeError("a verificacao encontrou diferencas; o destino NAO foi trocado. "
                               f"Relatorio: {json.dumps(relatorio['verificacao'], ensure_ascii=False)[:600]}")
        (tmp / "migracao.json").write_text(
            json.dumps(relatorio, indent=2, ensure_ascii=False), encoding="utf-8")
        if destino.exists():
            antigo = destino.parent / f"{destino.name}-anterior-{marca}"
            os.replace(destino, antigo)
            relatorio["destino_anterior"] = str(antigo)
        os.replace(tmp, destino)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    relatorio["segundos"] = round(time.time() - inicio, 1)
    relatorio["ok"] = True
    return relatorio


def comparar(cfg, *, amostra: int = 100, prazo: float = 600, origem: Path | None = None) -> dict:
    """Roda as mesmas consultas no Chroma e no SQLite e diz onde divergem.

    As consultas sao vetores reais de chunks do proprio indice SQLite. O Chroma
    e consultado num filho (pode cair); a comparacao e de sobreposicao entre os
    dez vizinhos, porque o Chroma e aproximado e o SQLite e exato.
    """
    from .indice_sqlite import ClienteSqlite

    origem = Path(origem or cfg.chroma_path)
    cliente = ClienteSqlite(cfg.sqlite_path)
    try:
        trabalho = Path.home() / ".delegation_core" / "migracao" / "comparar"
        trabalho.mkdir(parents=True, exist_ok=True)
        pedido: dict[str, str] = {}
        consultas: dict[str, np.ndarray] = {}
        for col in cliente.list_collections():
            n = col.count()
            if not n:
                continue
            passo = max(n // amostra, 1)
            vs = []
            for desloc in range(0, n, passo)[:amostra]:
                vs.append(col.get(limit=1, offset=desloc, include=["embeddings"])["embeddings"][0])
            consultas[col.name] = np.stack(vs)
            arquivo = trabalho / f"q-{col.name}.npy"
            np.save(arquivo, consultas[col.name])
            pedido[col.name] = str(arquivo)
        (trabalho / "pedido.json").write_text(json.dumps(pedido), encoding="utf-8")
        cmd = [sys.executable, "-m", "delegation_core.migracao_indice", "consultar",
               str(origem), str(trabalho / "pedido.json"), str(trabalho / "resposta.json")]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=prazo)
        except subprocess.TimeoutExpired:
            raise RuntimeError("o Chroma nao respondeu a tempo") from None
        if p.returncode != 0:
            raise RuntimeError(f"o Chroma nao respondeu (saida {p.returncode}): "
                               f"{(p.stderr.strip().splitlines() or [''])[-1]}")
        resposta = json.loads((trabalho / "resposta.json").read_text(encoding="utf-8"))
        saida: dict = {"colecoes": {}}
        for nome, qs in consultas.items():
            col = cliente.get_collection(nome)
            sobre = []
            piores = []
            for q, ids_chroma in zip(qs, resposta[nome]):
                meu = col.query(query_embeddings=[q.tolist()], n_results=VIZINHOS)["ids"][0]
                s = len(set(meu) & set(ids_chroma)) / VIZINHOS
                sobre.append(s)
                if s < 0.7:
                    piores.append({"sqlite": meu[:3], "chroma": ids_chroma[:3], "sobreposicao": s})
            saida["colecoes"][nome] = {
                "consultas": len(sobre), "linhas_sqlite": col.count(),
                "sobreposicao_media": round(float(np.mean(sobre)), 4),
                "consultas_com_menos_de_70pc": len(piores), "exemplos": piores[:3]}
        return saida
    finally:
        cliente.close()


if __name__ == "__main__":  # pragma: no cover - ponto de entrada do processo filho
    sys.exit(_principal_do_filho(sys.argv[1:]))
