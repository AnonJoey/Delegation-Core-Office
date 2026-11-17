"""Liga o pacote `recuperacao` ao `search_vault`: indice lexico do vault, reordenador, e quando usar.

## A regra, e por que ela e esta

Medido no vault real (ENRIQUECIMENTO.md, item 1), 60 perguntas parafraseadas:

| modo | R@1 | MRR@10 |
|---|---|---|
| denso (o que havia) | 0,433 | 0,533 |
| hibrido RRF sem reordenador | 0,250 | 0,420 |
| hibrido RRF + reordenador | 0,717 | 0,762 |

A fusao sozinha **piora** a pergunta de gente: o ruido lexico empurra o acerto
denso para baixo. Por isso hibrido e reordenador andam juntos. Quando o
reordenador nao esta disponivel (modelo nao baixado, placa sem espaco, config
desligada), a busca continua exatamente densa, como antes.

## Onde vale

Escopo `all` ou `notes`, sem `graph` e sem `client`. O indice lexico so conhece
as notas do vault; arquivo ingerido de fora e cliente nao estao nele, e fundir
uma lista filtrada com outra sem filtro devolveria o que o filtro existe para
tirar.

So `search_vault` (e a CLI) passam por aqui. `VaultManager.search` continua
densa para quem a usa por dentro: o merger decide fusao de notas pela
similaridade, e um acerto so lexico nao tem similaridade.

## O reordenador

`busca_reordenador_dispositivo`: "auto" usa a GPU se houver 1,5 GB livres na
hora de carregar, e senao desliga a reordenacao (em CPU ela custou 5,8 s por
consulta). "cuda" ou "cpu" forcam. O modelo nunca e baixado no meio de uma
busca: se nao estiver no cache local, a busca fica densa e o `doctor` diz.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("busca_hibrida")

_FM = re.compile(r"^---\n.*?\n---\n?", re.S)
_TITULO = re.compile(r"^title:\s*[\"']?(.*?)[\"']?\s*$", re.M)
_RELATED = re.compile(r"\n## Related\n(?:.*\n?)*?(?=\n## |\Z)")

#: Nao reescanear o disco a cada busca: 10 mil stats custam ~0,1 s.
INTERVALO_SINCRONIA = 30.0

_estado = {"indice": None, "sincronizado_em": 0.0, "reordenador": None, "motivo_sem_reordenador": ""}
_trava = threading.Lock()


def ler_nota(caminho: Path, tirar_related: bool = True) -> tuple[str, str]:
    """(titulo, corpo) sem frontmatter e sem o bloco `## Related` injetado pelo relink.

    O Related sai porque e lista de nomes de OUTRAS notas: na primeira medicao,
    o topo denso de uma pergunta sobre contencao de GPU foi uma nota cujo trecho
    casado era so o Related apontando para a nota certa.
    """
    t = caminho.read_text(encoding="utf-8", errors="ignore")
    fm = _FM.match(t)
    titulo = caminho.stem
    if fm:
        m = _TITULO.search(fm.group(0))
        if m and m.group(1).strip():
            titulo = m.group(1).strip()
        t = t[fm.end():]
    if tirar_related:
        t = _RELATED.sub("\n", t)
    return titulo, t


def ligado(cfg) -> bool:
    return bool(getattr(cfg, "busca_hibrida", True))


def aplicavel(cfg, scope: str, graph: str, client: str) -> bool:
    return ligado(cfg) and not graph and not client and (scope or "all") in ("all", "notes", "external")


def _e_gerada(caminho: Path) -> bool:
    try:
        with caminho.open(encoding="utf-8", errors="ignore") as f:
            return "graph_build" in f.read(600)
    except OSError:
        return False


def _abrir(cfg):
    """So abre o indice, sem sincronizar: quem sincroniza e `_indice` ou `sincronizar`.

    Separado porque `sincronizar()` sem indice chamava `_indice()`, que ja
    sincronizava por conta propria, e a primeira sincronia rodava duas vezes
    (pego pelo teste da sincronia externa, que conta o que foi gravado).
    """
    from .ranqueamento import IndiceLexico

    with _trava:
        if _estado["indice"] is None:
            _estado["indice"] = IndiceLexico(Path(cfg.vault) / ".lexico" / "indice.sqlite3")
        return _estado["indice"]


def _indice(cfg):
    idx = _abrir(cfg)
    with _trava:
        precisa = time.time() - _estado["sincronizado_em"] > INTERVALO_SINCRONIA
    if precisa:
        sincronizar(cfg, idx)
    return idx


def sincronizar(cfg, idx=None) -> dict:
    """Poe o indice lexico em dia com as notas escritas a mao (gerada fica de fora)."""
    from .listagem_vault import notas_do_vault

    # `is None`, e nao `or`: IndiceLexico tem __len__, entao um indice VAZIO e
    # falso, e `idx or _indice(cfg)` recursava _indice -> sincronizar -> _indice
    # ate estourar a pilha. Era exatamente o caso da primeira busca de um vault
    # novo, que caia para densa em silencio. Achado pelo teste, antes de rodar.
    if idx is None:
        idx = _abrir(cfg)
    raiz = Path(cfg.vault)
    docs = []
    for rel in notas_do_vault(cfg):
        p = raiz / rel
        if "/graphs/" in f"/{rel}":
            continue
        try:
            m = p.stat().st_mtime
        except OSError:
            continue
        def ler(p=p):
            if _e_gerada(p):
                return ("", "")
            return ler_nota(p)
        docs.append((rel, m, ler))
    r = idx.atualizar(docs)
    with _trava:
        _estado["sincronizado_em"] = time.time()
    return r


def esquecer_caminho(cfg, rel: str) -> None:
    """Tira uma nota do indice lexico ja, sem esperar a proxima sincronia."""
    try:
        # So se ja estiver aberto: abrir criaria .lexico/ num vault que nem usa
        # a busca hibrida, e um indice aberto depois sincroniza de qualquer jeito.
        with _trava:
            idx = _estado["indice"]
        if idx is not None:
            idx.remover(rel)
    except Exception as e:  # noqa: BLE001 - a sincronia seguinte resolve
        logger.debug("indice lexico nao tirou %s: %s", rel, e)


# ── arquivos ingeridos (scope external) ─────────────────────────────────────
#
# O indice lexico de cima so conhece nota do vault. Arquivo ingerido de fora
# (ingest_folder) nao esta no disco do vault e reextrair PDF ou docx a cada
# sincronia seria caro; o texto de cada pedaco ja esta no ChromaDB. Este segundo
# indice e montado a partir dele, pedaco por pedaco, e a versao de cada pedaco e
# o `ingested_at` que o ingest grava. Medido no teste ponta a ponta de 27/09: a
# busca externa, so densa, pos uma captura de tela na posicao 6 para uma frase
# que estava nela.

_PEDACO = re.compile(r"::chunk_\d+$")
_PAGINA = 2000


def _versao(meta: dict) -> float:
    try:
        return datetime.fromisoformat(str(meta.get("ingested_at", ""))).timestamp()
    except ValueError:
        return 0.0


def _abrir_externo(vault):
    from .ranqueamento import IndiceLexico

    with _trava:
        if _estado.get("indice_externo") is None:
            _estado["indice_externo"] = IndiceLexico(Path(vault.cfg.vault) / ".lexico" / "externo.sqlite3")
        return _estado["indice_externo"]


def _indice_externo(vault):
    """O indice externo como esta, disparando a sincronia em segundo plano se vencida.

    Nunca sincroniza dentro da busca. Medido na copia do indice real: a
    PRIMEIRA sincronia de 26.905 pedacos levou 183 s, o que estouraria a
    chamada MCP; a incremental leva 0,9 s, que ainda nao e custo para por em
    toda busca. Enquanto o indice estiver vazio, a busca externa fica densa.
    """
    idx = _abrir_externo(vault)
    with _trava:
        vencida = time.time() - _estado.get("externo_sincronizado_em", 0.0) > INTERVALO_SINCRONIA
        rodando = _estado.get("externo_sincronizando", False)
        if vencida and not rodando:
            _estado["externo_sincronizando"] = True
            disparar = True
        else:
            disparar = False
    if disparar:
        def _rodar():
            try:
                sincronizar_externo(vault, idx)
            except Exception as e:  # noqa: BLE001
                logger.warning("sincronia do lexico externo falhou: %s", e)
            finally:
                with _trava:
                    _estado["externo_sincronizando"] = False
        threading.Thread(target=_rodar, name="lexico-externo", daemon=True).start()
    return idx


def sincronizar_externo(vault, idx=None) -> dict:
    """Poe o indice lexico dos ingeridos em dia com as linhas do ChromaDB, em paginas.

    Paginado porque um `get` unico de dezenas de milhares de linhas estoura o
    limite de variaveis do SQLite do Chroma ("too many SQL variables", visto em
    27/09 na copia do indice real).
    """
    if idx is None:
        idx = _abrir_externo(vault)
    col = vault.collection
    antes = idx.mtimes()
    vistos: dict[str, float] = {}
    offset = 0
    while True:
        pag = col.get(where={"is_external": "true"}, include=["metadatas"], limit=_PAGINA, offset=offset)
        ids = pag.get("ids") or []
        for i, m in zip(ids, pag.get("metadatas") or []):
            vistos[i] = _versao(m or {})
        if len(ids) < _PAGINA:
            break
        offset += _PAGINA
    novos = [i for i, v in vistos.items() if antes.get(i) != v]
    for k in range(0, len(novos), 200):
        lote = novos[k:k + 200]
        r = col.get(ids=lote, include=["documents", "metadatas"])
        for i, doc, m in zip(r.get("ids") or [], r.get("documents") or [], r.get("metadatas") or []):
            idx.gravar(i, vistos[i], (m or {}).get("title", ""), doc or "")
    removidos = 0
    for i in set(antes) - set(vistos):
        idx.remover(i)
        removidos += 1
    with _trava:
        _estado["externo_sincronizado_em"] = time.time()
    return {"gravados": len(novos), "removidos": removidos, "total": len(idx)}


def buscar_externo_lexico(vault, consulta: str, limite: int = 30) -> list[tuple[str, float, str]]:
    """(caminho do arquivo, pontuacao, id do melhor pedaco), um por arquivo, do melhor ao pior."""
    idx = _indice_externo(vault)
    if len(idx) == 0:
        return []
    saida, vistos = [], set()
    for pid, sc in idx.buscar(consulta, limite * 4):
        caminho = _PEDACO.sub("", pid)
        if caminho in vistos:
            continue
        vistos.add(caminho)
        saida.append((caminho, sc, pid))
        if len(saida) >= limite:
            break
    return saida


def _modelo_no_cache(modelo: str) -> bool:
    try:
        from huggingface_hub import try_to_load_from_cache
        return isinstance(try_to_load_from_cache(modelo, "config.json"), str)
    except Exception:
        return False


def _gpu_livre_mb() -> int:
    try:
        import torch
        if not torch.cuda.is_available():
            return 0
        livre, _ = torch.cuda.mem_get_info()
        return int(livre / 2**20)
    except Exception:
        return 0


def reordenador(cfg):
    """O reordenador, carregado uma vez, ou None com o motivo em `_estado`."""
    from .ranqueamento import CrossEncoderReordenador
    from .ranqueamento.rerank import MODELO_PADRAO

    with _trava:
        if _estado["reordenador"] is not None:
            return _estado["reordenador"]
    if not getattr(cfg, "busca_reordenar", True):
        _estado["motivo_sem_reordenador"] = "busca_reordenar=false"
        return None
    modelo = getattr(cfg, "busca_reordenador_modelo", "") or MODELO_PADRAO
    if not _modelo_no_cache(modelo):
        _estado["motivo_sem_reordenador"] = f"modelo {modelo} nao esta no cache local"
        return None
    disp = getattr(cfg, "busca_reordenador_dispositivo", "auto") or "auto"
    if disp == "auto":
        if _gpu_livre_mb() >= 1500:
            disp = "cuda"
        else:
            _estado["motivo_sem_reordenador"] = "sem 1,5 GB livres na GPU (em CPU custa 5,8 s por busca)"
            return None
    r = CrossEncoderReordenador(modelo=modelo, dispositivo=disp,
                                max_caracteres=int(getattr(cfg, "busca_caracteres_rerank", 2000)))
    with _trava:
        _estado["reordenador"] = r
        _estado["motivo_sem_reordenador"] = ""
    return r


def situacao(cfg) -> dict:
    """Para o doctor e o heartbeat: o que esta ligado e, se nao, por que."""
    return {
        "ligada": ligado(cfg),
        "reordenador_carregado": _estado["reordenador"] is not None,
        "motivo_sem_reordenador": _estado["motivo_sem_reordenador"],
        "notas_no_indice_lexico": len(_estado["indice"]) if _estado["indice"] is not None else None,
    }


def buscar(vault, query: str, limit: int = 5, scope: str = "all", snippet_chars: int = 800,
           folder: str = "") -> list[dict] | None:
    """A lista de acertos no mesmo formato de `VaultManager.search`, ou None para cair no denso."""
    from .ranqueamento import combinar

    cfg = vault.cfg
    reord = reordenador(cfg)
    if reord is None:
        return None
    try:
        densos = vault.search(query, limit=max(limit, 30), scope=scope, snippet_chars=snippet_chars,
                              **({"folder": folder} if folder else {}))
        if densos and "error" in densos[0]:
            return None
        pedaco_de: dict[str, str] = {}
        if scope == "external":
            ext = buscar_externo_lexico(vault, query, 30)
            if not ext and len(_abrir_externo(vault)) == 0:
                return None  # indice externo ainda sendo montado: fica densa
            pontuados = [(c, sc) for c, sc, _ in ext]
            pedaco_de = {c: pid for c, _, pid in ext}
        else:
            idx = _indice(cfg)
            pontuados = idx.buscar(query, 30 if not folder else 200)
            if folder:
                pontuados = [(p, sc) for p, sc in pontuados if p.split("/", 1)[0] == folder][:30]
        lexicos = [p for p, _ in pontuados]
    except Exception as e:  # noqa: BLE001
        logger.warning("busca hibrida caiu para densa: %s", e)
        return None

    por_caminho = {h["path"]: h for h in densos}
    raiz = Path(cfg.vault)
    textos: dict[str, str] = {}

    def texto_de(rel: str) -> str:
        if rel not in textos:
            if scope == "external":
                # arquivo ingerido: o texto e o do pedaco que casou, guardado no
                # indice lexico; sem ele, o trecho que a busca densa devolveu
                guardado = _estado["indice_externo"].ler(pedaco_de[rel]) if rel in pedaco_de else None
                textos[rel] = (f"{guardado[0]}\n{guardado[1]}" if guardado
                               else por_caminho.get(rel, {}).get("snippet", ""))
                return textos[rel]
            try:
                t, c = ler_nota(raiz / rel)
                textos[rel] = f"{t}\n{c}"
            except OSError:
                textos[rel] = por_caminho.get(rel, {}).get("snippet", "")
        return textos[rel]

    try:
        ordem = combinar(query, [h["path"] for h in densos], lexicos, limite=limit,
                         reordenador=reord, texto_de=texto_de,
                         profundidade_rerank=int(getattr(cfg, "busca_profundidade_rerank", 20)),
                         pontos_lexicos=[s for _, s in pontuados],
                         razao_dominante=float(getattr(cfg, "busca_razao_lexico_dominante", 1.5)) or None)
    except Exception as e:  # noqa: BLE001
        logger.warning("reordenacao falhou, busca caiu para densa: %s", e)
        return None

    saida = []
    for rel in ordem:
        if rel in por_caminho:
            h = dict(por_caminho[rel])
            h["fonte"] = "denso+lexico" if rel in lexicos else "denso"
        elif scope == "external":
            guardado = _estado["indice_externo"].ler(pedaco_de.get(rel, "")) or (Path(rel).stem, "")
            h = {"title": guardado[0] or Path(rel).stem, "path": rel, "folder": "_external",
                 "kind": "external", "subkind": "external", "client": "",
                 "snippet": guardado[1].strip()[:max(snippet_chars, 0)],
                 "similarity": 0.0, "fonte": "lexico"}
        else:
            # O indice lexico sincroniza a cada 30 s; uma nota apagada, movida
            # ou esquecida nesse intervalo ainda aparece nele. Achado no
            # test-drive de 05/10: vault_forget_note e, no mesmo segundo, um
            # search_vault que caia com FileNotFoundError em vez de responder.
            try:
                titulo, corpo = ler_nota(raiz / rel)
            except OSError:
                esquecer_caminho(cfg, rel)
                continue
            h = {"title": titulo, "path": rel, "folder": rel.split("/")[0],
                 "kind": "note", "subkind": "curated", "client": "",
                 "snippet": corpo.strip()[:max(snippet_chars, 0)],
                 # sem similaridade densa: nao inventar uma. 0,0 deixa a
                 # confianca do search_vault vir so de evidencia densa.
                 "similarity": 0.0, "fonte": "lexico"}
        saida.append(h)
    return saida
