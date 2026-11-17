"""A busca hibrida ligada ao search_vault: quando vale, o que devolve, e quando cai para densa."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import delegation_core.server as server
from delegation_core import busca_hibrida
# importado antes do fixture autouse trocar a funcao: e o original
from delegation_core.busca_hibrida import reordenador as REORDENADOR_REAL
from delegation_core.config import Config


class Dublê:
    """Pontua pela contagem da palavra 'alvo' no texto que recebe."""

    def __init__(self):
        self.textos = []

    def pontuar(self, consulta, textos):
        self.textos.extend(textos)
        return [float(t.count("alvo")) for t in textos]


class VaultFalso:
    def __init__(self, cfg, densos):
        self.cfg = cfg
        self._densos = densos
        self.chamadas = []

    def search(self, query, limit=5, scope="all", graph="", snippet_chars=800, client="", folder=""):
        # mesma assinatura do VaultManager.search: um duble que recusa um
        # parametro que a API aceita faz a busca cair para densa por TypeError,
        # e o teste mede o fallback em vez da regra
        self.chamadas.append({"limit": limit, "scope": scope, "folder": folder})
        return [dict(h) for h in self._densos if not folder or h["path"].startswith(folder + "/")][:limit]


def _hit(path, sim):
    return {"title": path, "path": path, "folder": path.split("/")[0], "kind": "note",
            "subkind": "curated", "client": "", "snippet": "trecho de " + path, "similarity": sim}


@pytest.fixture
def cfg(tmp_path):
    raiz = tmp_path / "vault"
    for pasta in ("Fixes", "Reference"):
        (raiz / pasta).mkdir(parents=True)
    (raiz / "Fixes" / "denso.md").write_text("---\ntitle: Denso\n---\nnada aqui\n")
    (raiz / "Fixes" / "lexico.md").write_text(
        "---\ntitle: Lexico\n---\nfala de embed_device e alvo alvo\n\n## Related\n- [[denso]]\n")
    (raiz / "Fixes" / "related.md").write_text(
        "---\ntitle: So related\n---\ncorpo curto embed_device\n\n## Related\n- [[alvo alvo alvo]]\n")
    (raiz / "Reference" / "gerada.md").write_text("---\nsource: graph_build\n---\nembed_device alvo\n")
    return Config(vault_path=str(raiz), vault_folders=["Fixes", "Reference"])


def test_aplicavel_so_em_all_e_notes_sem_graph_e_sem_cliente(cfg):
    assert busca_hibrida.aplicavel(cfg, "all", "", "")
    assert busca_hibrida.aplicavel(cfg, "notes", "", "")
    assert busca_hibrida.aplicavel(cfg, "external", "", "")
    assert not busca_hibrida.aplicavel(cfg, "generated", "", "")
    assert not busca_hibrida.aplicavel(cfg, "all", "meu-grafo", "")
    assert not busca_hibrida.aplicavel(cfg, "all", "", "gazin")
    cfg.busca_hibrida = False
    assert not busca_hibrida.aplicavel(cfg, "all", "", "")


def test_sem_reordenador_cai_para_densa(cfg):
    """A fusao sem reordenador piorou a parafrase (R@1 0,433 -> 0,250): nao roda sozinha."""
    assert busca_hibrida.buscar(VaultFalso(cfg, [_hit("Fixes/denso.md", 0.7)]), "x") is None


def test_hibrida_traz_acerto_so_lexico_e_reordena(cfg, monkeypatch):
    d = Dublê()
    monkeypatch.setattr(busca_hibrida, "reordenador", lambda c: d)
    v = VaultFalso(cfg, [_hit("Fixes/denso.md", 0.7)])
    r = busca_hibrida.buscar(v, "embed_device", limit=5)
    assert r[0]["path"] == "Fixes/lexico.md" and r[0]["fonte"] == "lexico"
    assert r[0]["similarity"] == 0.0 and r[0]["title"] == "Lexico"
    assert {h["path"] for h in r} >= {"Fixes/denso.md", "Fixes/lexico.md"}
    assert v.chamadas[0]["limit"] == 30  # pede candidatos alem do limite


def test_related_sai_do_texto_que_o_reordenador_le(cfg, monkeypatch):
    """Sem tirar o Related, 'related.md' pontuaria 3 pelo nome de outra nota."""
    d = Dublê()
    monkeypatch.setattr(busca_hibrida, "reordenador", lambda c: d)
    r = busca_hibrida.buscar(VaultFalso(cfg, []), "embed_device", limit=5)
    assert [h["path"] for h in r][0] == "Fixes/lexico.md"
    assert not any("alvo alvo alvo" in t for t in d.textos)


def test_nota_gerada_fica_fora_do_indice_lexico(cfg, monkeypatch):
    monkeypatch.setattr(busca_hibrida, "reordenador", lambda c: Dublê())
    r = busca_hibrida.buscar(VaultFalso(cfg, []), "embed_device", limit=10)
    assert "Reference/gerada.md" not in [h["path"] for h in r]


def test_erro_do_denso_cai_para_densa(cfg, monkeypatch):
    monkeypatch.setattr(busca_hibrida, "reordenador", lambda c: Dublê())
    v = VaultFalso(cfg, [{"error": "Vault not initialized"}])
    assert busca_hibrida.buscar(v, "x") is None


def test_reordenador_que_quebra_cai_para_densa(cfg, monkeypatch):
    class Quebra:
        def pontuar(self, q, t):
            raise RuntimeError("CUDA out of memory")
    monkeypatch.setattr(busca_hibrida, "reordenador", lambda c: Quebra())
    assert busca_hibrida.buscar(VaultFalso(cfg, [_hit("Fixes/denso.md", 0.7)]), "embed_device") is None


# ── escolha do reordenador ──────────────────────────────────────────────────

def test_reordenador_desligado_por_config(cfg):
    cfg.busca_reordenar = False
    assert REORDENADOR_REAL(cfg) is None
    assert busca_hibrida._estado["motivo_sem_reordenador"] == "busca_reordenar=false"


def test_reordenador_nunca_baixa_modelo_no_meio_da_busca(cfg, monkeypatch):
    monkeypatch.setattr(busca_hibrida, "_modelo_no_cache", lambda m: False)
    assert REORDENADOR_REAL(cfg) is None
    assert "cache local" in busca_hibrida._estado["motivo_sem_reordenador"]


def test_auto_sem_gpu_nao_reordena_em_cpu(cfg, monkeypatch):
    monkeypatch.setattr(busca_hibrida, "_modelo_no_cache", lambda m: True)
    monkeypatch.setattr(busca_hibrida, "_gpu_livre_mb", lambda: 800)
    assert REORDENADOR_REAL(cfg) is None
    assert "GPU" in busca_hibrida._estado["motivo_sem_reordenador"]


def test_auto_com_gpu_escolhe_cuda_sem_carregar(cfg, monkeypatch):
    monkeypatch.setattr(busca_hibrida, "_modelo_no_cache", lambda m: True)
    monkeypatch.setattr(busca_hibrida, "_gpu_livre_mb", lambda: 4000)
    r = REORDENADOR_REAL(cfg)
    assert r.dispositivo == "cuda" and r._ce is None and r.max_caracteres == 2000
    assert REORDENADOR_REAL(cfg) is r  # uma vez por processo


def test_cpu_forcado_e_respeitado(cfg, monkeypatch):
    monkeypatch.setattr(busca_hibrida, "_modelo_no_cache", lambda m: True)
    monkeypatch.setattr(busca_hibrida, "_gpu_livre_mb", lambda: 0)
    cfg.busca_reordenador_dispositivo = "cpu"
    assert REORDENADOR_REAL(cfg).dispositivo == "cpu"


# ── ligacao no search_vault ─────────────────────────────────────────────────

def _search_vault(monkeypatch, cfg, densos, **kw):
    v = VaultFalso(cfg, densos)
    monkeypatch.setattr(server, "_vault", v)
    monkeypatch.setattr(server, "_engine", SimpleNamespace(cfg=cfg))
    monkeypatch.setattr(cfg, "route", lambda **k: "agent", raising=False)
    return json.loads(asyncio.run(server.search_vault(query="embed_device", **kw))), v


def test_search_vault_diz_que_foi_hibrida(cfg, monkeypatch):
    monkeypatch.setattr(busca_hibrida, "reordenador", lambda c: Dublê())
    r, _ = _search_vault(monkeypatch, cfg, [_hit("Fixes/denso.md", 0.7)], scope="all")
    assert r["quality"]["retrieval"] == "hybrid+rerank"
    assert r["sources"][0]["path"] == "Fixes/lexico.md"
    assert r["quality"]["top_similarity"] == 0.7


def test_search_vault_sem_reordenador_e_densa(cfg, monkeypatch):
    r, v = _search_vault(monkeypatch, cfg, [_hit("Fixes/denso.md", 0.7)], scope="all")
    assert r["quality"]["retrieval"] == "dense" and [s["path"] for s in r["sources"]] == ["Fixes/denso.md"]


def test_search_vault_com_grafo_nao_passa_pela_hibrida(cfg, monkeypatch):
    chamado = []
    monkeypatch.setattr(busca_hibrida, "buscar", lambda *a, **k: chamado.append(1))
    r, _ = _search_vault(monkeypatch, cfg, [_hit("Fixes/denso.md", 0.7)], graph="g")
    assert chamado == [] and r["quality"]["retrieval"] == "dense"


def test_acerto_lexico_dominante_nao_e_desmontado_pelo_reordenador(cfg, monkeypatch):
    """O Dublê pontua 'alvo'; related.md so tem embed_device no corpo curto, e
    lexico.md tem 'alvo alvo'. A busca por um termo que so uma nota tem, com BM25
    muito acima das outras, deixa essa nota no topo mesmo com o reordenador contra."""
    (cfg.vault / "Fixes" / "unica.md").write_text("---\ntitle: Unica\n---\nzebrafenix zebrafenix zebrafenix\n")
    monkeypatch.setattr(busca_hibrida, "reordenador", lambda c: Dublê())
    r = busca_hibrida.buscar(VaultFalso(cfg, [_hit("Fixes/lexico.md", 0.7)]), "zebrafenix", limit=5)
    assert r[0]["path"] == "Fixes/unica.md"
    cfg.busca_razao_lexico_dominante = 0
    busca_hibrida._estado["sincronizado_em"] = 0
    r = busca_hibrida.buscar(VaultFalso(cfg, [_hit("Fixes/lexico.md", 0.7)]), "zebrafenix", limit=5)
    assert r[0]["path"] == "Fixes/lexico.md"


def test_pasta_vale_tambem_para_o_candidato_lexico(cfg, monkeypatch):
    """O unico acerto lexico de embed_device fora de Reference esta em Fixes: com
    folder=Reference ele nao pode entrar, mesmo sendo o melhor lexico."""
    monkeypatch.setattr(busca_hibrida, "reordenador", lambda c: Dublê())
    r = busca_hibrida.buscar(VaultFalso(cfg, []), "embed_device", limit=5, folder="Reference")
    assert all(h["path"].startswith("Reference/") for h in r)



# ── arquivos ingeridos (scope external) ─────────────────────────────────────

class ColecaoFalsa:
    """Imita o get paginado do Chroma e RECUSA pagina grande demais, como o real."""

    def __init__(self, linhas):
        self.linhas = linhas  # id -> (meta, doc)
        self.paginas = 0

    def get(self, where=None, ids=None, include=(), limit=None, offset=0):
        if ids is not None:
            sel = [i for i in ids if i in self.linhas]
        else:
            if limit is None or limit > 5000:
                raise RuntimeError("too many SQL variables")
            self.paginas += 1
            todos = [i for i, (m, _) in self.linhas.items() if m.get("is_external") == "true"]
            sel = todos[offset:offset + limit]
        return {"ids": sel, "metadatas": [self.linhas[i][0] for i in sel],
                "documents": [self.linhas[i][1] for i in sel]}


def _ext(path, n, texto, quando="2026-09-01T10:00:00"):
    return {f"{path}::chunk_{n}": ({"is_external": "true", "title": path.rsplit("/", 1)[-1],
                                    "ingested_at": quando}, texto)}


def test_sincronia_externa_pagina_e_so_regrava_o_que_mudou(cfg, monkeypatch):
    monkeypatch.setattr(busca_hibrida, "_PAGINA", 2)
    linhas = {}
    for i in range(5):
        linhas.update(_ext(f"/docs/a{i}.md", 0, f"texto numero {i}"))
    linhas["nota"] = ({"is_external": "false"}, "nao entra")
    v = SimpleNamespace(cfg=cfg, collection=ColecaoFalsa(linhas))
    r = busca_hibrida.sincronizar_externo(v)
    assert r == {"gravados": 5, "removidos": 0, "total": 5} and v.collection.paginas == 3
    linhas.update(_ext("/docs/a0.md", 0, "texto trocado", quando="2026-09-02T10:00:00"))
    del linhas["/docs/a4.md::chunk_0"]
    assert busca_hibrida.sincronizar_externo(v) == {"gravados": 1, "removidos": 1, "total": 4}


def test_lexico_externo_colapsa_pedacos_no_arquivo(cfg):
    linhas = {**_ext("/docs/guia.md", 0, "zebrafenix aqui"), **_ext("/docs/guia.md", 1, "zebrafenix zebrafenix"),
              **_ext("/docs/outro.md", 0, "zebrafenix")}
    v = SimpleNamespace(cfg=cfg, collection=ColecaoFalsa(linhas))
    busca_hibrida.sincronizar_externo(v)
    r = busca_hibrida.buscar_externo_lexico(v, "zebrafenix")
    assert [c for c, _, _ in r] == ["/docs/guia.md", "/docs/outro.md"]
    assert r[0][2] == "/docs/guia.md::chunk_1"


def test_busca_externa_traz_acerto_so_lexico_com_o_texto_do_pedaco(cfg, monkeypatch):
    linhas = {**_ext("/docs/guia.md", 0, "o downloader procura o asset avx2 alvo alvo"),
              **_ext("/docs/ruido.md", 0, "nada a ver")}
    d = Dublê()
    monkeypatch.setattr(busca_hibrida, "reordenador", lambda c: d)
    v = VaultFalso(cfg, [])
    v.collection = ColecaoFalsa(linhas)
    # a primeira busca nao espera a montagem do indice: fica densa (aqui, vazia).
    # A sincronia de fundo e segurada, senao a corrida com a thread decide o teste.
    real = busca_hibrida.sincronizar_externo
    monkeypatch.setattr(busca_hibrida, "sincronizar_externo", lambda vault, idx=None: {})
    assert busca_hibrida.buscar(v, "downloader asset avx2", limit=3, scope="external") is None
    monkeypatch.setattr(busca_hibrida, "sincronizar_externo", real)
    busca_hibrida.sincronizar_externo(v)
    r = busca_hibrida.buscar(v, "downloader asset avx2", limit=3, scope="external")
    assert r[0]["path"] == "/docs/guia.md" and r[0]["kind"] == "external" and r[0]["fonte"] == "lexico"
    assert any("asset avx2" in t for t in d.textos)



def test_sincronia_externa_roda_em_segundo_plano_uma_de_cada_vez(cfg, monkeypatch):
    """A busca nunca espera a sincronia (a primeira levou 183 s no indice real)."""
    import threading
    liberar = threading.Event()
    chamadas = []

    def lenta(vault, idx=None):
        chamadas.append(1)
        liberar.wait(5)
        return {}
    monkeypatch.setattr(busca_hibrida, "sincronizar_externo", lenta)
    v = SimpleNamespace(cfg=cfg, collection=ColecaoFalsa({}))
    t = __import__("time").time()
    busca_hibrida._indice_externo(v)
    busca_hibrida._indice_externo(v)
    assert __import__("time").time() - t < 1 and len(chamadas) == 1
    liberar.set()


def test_nota_que_sumiu_entre_sincronias_nao_derruba_a_busca(cfg, monkeypatch):
    """Achado no test-drive de 05/10: esquecer uma nota e buscar no mesmo
    segundo dava FileNotFoundError, porque o indice lexico so sincroniza a
    cada 30 s e ainda apontava para o arquivo."""
    monkeypatch.setattr(busca_hibrida, "reordenador", lambda c: Dublê())
    v = VaultFalso(cfg, [_hit("Fixes/denso.md", 0.7)])
    assert busca_hibrida.buscar(v, "embed_device")[0]["path"] == "Fixes/lexico.md"
    (Path(cfg.vault) / "Fixes" / "lexico.md").unlink()
    r = busca_hibrida.buscar(v, "embed_device")
    assert "Fixes/lexico.md" not in [h["path"] for h in r]
    assert "Fixes/lexico.md" not in [p for p, _ in busca_hibrida._abrir(cfg).buscar("embed_device", 30)]
