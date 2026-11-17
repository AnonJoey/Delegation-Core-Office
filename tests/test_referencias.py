"""Caminho citado em nota conferido contra o disco (referencias/ e referencias_vault)."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import delegation_core.server as server
from delegation_core import referencias_vault as rv
from delegation_core.referencias import extrair, verificar

CASA = "/home/eu"


def caminhos(texto):
    return [r.caminho for r in extrair(texto, casa=CASA)]


def test_extrai_so_caminho_local_entre_crases():
    t = ("veja `~/.hermes/config.yaml:490`, `/mnt/Expansion/x/`. e `/home/eu/a.md`, "
         "mas nao `/loop`, `/api/status`, `/Users/saad/`, `/home/outro/b`, `/mnt/c/Users/j`, "
         "`~/{a,b}`, `/mnt/<disco>/x`, `/usr/share/...`, nem /home/eu/sem-crase")
    assert caminhos(t) == ["/home/eu/.hermes/config.yaml", "/mnt/Expansion/x/", "/home/eu/a.md"]
    assert extrair(t, casa=CASA)[0].bruto == "~/.hermes/config.yaml:490"


def test_repeticao_conta_uma_vez():
    assert caminhos("`/home/eu/a` e `/home/eu/a` e `~/a`") == ["/home/eu/a"]


def test_verificar_ancestral_e_sugestao():
    existe = {"/home/eu", "/home/eu/docs", "/srv/novo/proj/cfg/app.yaml", "/usr/bin/app.yaml"}.__contains__
    refs = verificar(extrair("`/home/eu/docs/proj/cfg/app.yaml` `/home/eu/docs`", casa=CASA), existe=existe,
                     localizar=lambda nome: ["/usr/bin/app.yaml", "/srv/novo/proj/cfg/app.yaml", "/x/sumiu/app.yaml"])
    morta, viva = refs
    assert viva.existe and not viva.sugestoes and not viva.ancestral
    assert morta.existe is False and morta.ancestral == "/home/eu/docs"
    # so a que divide 3 componentes finais; a de /usr/bin e homonima por acaso
    assert morta.sugestoes == ["/srv/novo/proj/cfg/app.yaml"]
    assert morta.como_dict()["now_at"] == ["/srv/novo/proj/cfg/app.yaml"]


def test_localizar_que_quebra_nao_derruba():
    def ruim(nome):
        raise OSError("sem indice")
    [r] = verificar(extrair("`/home/eu/z`", casa=CASA), existe=lambda p: False, localizar=ruim)
    assert r.existe is False and r.sugestoes == [] and r.ancestral == ""


def _vault(tmp_path):
    raiz = tmp_path / "v"
    for pasta in ("Fixes", "Sessions", "Reference"):
        (raiz / pasta).mkdir(parents=True)
    vivo = tmp_path / "vivo.txt"
    vivo.write_text("x")
    (raiz / "Fixes" / "a.md").write_text(f"abra `{vivo}` e `{tmp_path}/sumiu/b.conf`")
    (raiz / "Sessions" / "s.md").write_text(f"naquele dia: `{tmp_path}/sumiu/b.conf`")
    (raiz / "Reference" / "t-transcript-1.md").write_text(f"`{tmp_path}/sumiu/c`")
    (raiz / "Reference" / "g.md").write_text(f"---\ngerado_por: sonho\n---\n`{tmp_path}/sumiu/d`")
    return SimpleNamespace(vault=raiz, referencias_enabled=True), tmp_path


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _casa(tmp_path, monkeypatch):
    """As notas de teste citam caminhos em tmp_path, que passa a ser a casa."""
    monkeypatch.setattr(rv, "CASA", str(tmp_path))
    rv._CACHE.clear()


def test_marcar_na_busca_pula_nota_historica(tmp_path):
    cfg, base = _vault(tmp_path)
    hits = [{"path": "Fixes/a.md"}, {"path": "Sessions/s.md"}, {"path": "Reference/t-transcript-1.md"},
            {"path": "Reference/g.md"}, {"path": "fora.pdf"}]
    rv.marcar_mortas(cfg, hits)
    assert hits[0]["dead_refs"] == [f"{base}/sumiu/b.conf"]
    assert all("dead_refs" not in h for h in hits[1:])
    cfg.referencias_enabled = False
    h = [{"path": "Fixes/a.md"}]
    rv.marcar_mortas(cfg, h)
    assert h == [{"path": "Fixes/a.md"}]


def test_cache_segue_o_mtime(tmp_path):
    cfg, base = _vault(tmp_path)
    assert rv.mortas(cfg, "Fixes/a.md")
    nota = cfg.vault / "Fixes" / "a.md"
    import os
    nota.write_text("nada citado")
    st = nota.stat()
    os.utime(nota, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000))
    assert rv.mortas(cfg, "Fixes/a.md") == []


def test_varrer(tmp_path):
    cfg, base = _vault(tmp_path)
    r = rv.varrer(cfg, localizar=lambda n: [])
    assert (r["paths_cited"], r["paths_dead"], r["notes_with_dead"]) == (2, 1, 1)
    assert r["notes"][0]["note"] == "Fixes/a.md"
    assert r["notes"][0]["dead"][0]["nearest_existing"] == str(base)


class VaultFalso:
    def __init__(self, cfg):
        self.cfg = cfg

    def find_notes_by_stem(self, nome):
        return [p for p in self.cfg.vault.rglob("*.md") if p.stem == nome]


def test_ferramenta(tmp_path, monkeypatch):
    cfg, base = _vault(tmp_path)
    monkeypatch.setattr(server, "_vault", VaultFalso(cfg))
    monkeypatch.setattr(rv, "localizar_plocate", lambda n, limite=200: [])
    r = json.loads(asyncio.run(server.vault_dead_refs(note="a")))
    assert r["cited"] == 2 and [d["path"] for d in r["dead"]] == [f"{base}/sumiu/b.conf"]
    assert "historical" not in r
    assert json.loads(asyncio.run(server.vault_dead_refs(note="s")))["historical"] is True
    assert json.loads(asyncio.run(server.vault_dead_refs(folder="Fixes")))["notes_with_dead"] == 1
    assert json.loads(asyncio.run(server.vault_dead_refs(note="naoha")))["error_type"] == "not_found"
    assert json.loads(asyncio.run(server.vault_dead_refs(folder="Nada")))["error_type"] == "not_found"


def test_search_vault_marca_dead_refs(tmp_path, monkeypatch):
    from delegation_core.config import Config
    _, base = _vault(tmp_path)
    cfg = Config(vault_path=str(tmp_path / "v"), vault_folders=["Fixes"], recordacao_enabled=False,
                 busca_hibrida=False, sonho_enabled=False)

    class V(VaultFalso):
        def search(self, query, **k):
            return [{"path": "Fixes/a.md", "title": "a", "similarity": 0.7, "snippet": ""}]

    monkeypatch.setattr(server, "_vault", V(cfg))
    monkeypatch.setattr(server, "_engine", SimpleNamespace(cfg=cfg))
    r = json.loads(asyncio.run(server.search_vault(query="conf", scope="notes")))
    assert r["sources"][0]["dead_refs"] == [f"{base}/sumiu/b.conf"]


def test_casa_do_config_vence_o_home(tmp_path, monkeypatch):
    monkeypatch.setattr(rv, "CASA", None)
    cfg, base = _vault(tmp_path)
    (cfg.vault / "Fixes" / "til.md").write_text("abra `~/vivo.txt` e `~/sumiu.txt`")
    cfg.referencias_casa = str(base)
    assert rv.mortas(cfg, "Fixes/til.md") == [f"{base}/sumiu.txt"]
