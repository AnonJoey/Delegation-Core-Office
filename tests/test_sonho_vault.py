"""A ligacao do sonho: recordacao no search_vault, o sonho com modelo e vault falsos, e as ferramentas."""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

import delegation_core.server as server
from delegation_core import sonho_vault
from delegation_core.config import Config

#: Data de hoje: o sonho escolhe as notas recentes pela data do nome. Uma data
#: fixa no nome fez a suite falhar 9 dias depois de escrita (05/10/2026).
HOJE = datetime.now().strftime("%Y-%m-%d")
AMANHA = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")


class VaultFalso:
    """search devolve as notas do vault em ordem fixa; index_note aceita tudo."""

    def __init__(self, cfg, ordem):
        self.cfg = cfg
        self.ordem = ordem
        self.buscas = []

    def search(self, query, limit=5, scope="all", graph="", snippet_chars=800, client=""):
        self.buscas.append(query)
        return [{"path": p, "title": p, "similarity": 0.7, "snippet": ""} for p in self.ordem][:limit]

    def index_note(self, texto, meta):
        return True

    def stamp_indexed(self, rels):
        pass


@pytest.fixture
def base(tmp_path, monkeypatch):
    raiz = tmp_path / "vault"
    for pasta in ("Fixes", "Decisions", "Sessions", "Reference"):
        (raiz / pasta).mkdir(parents=True)
    (raiz / "Decisions" / "2026-09-02-BGE na CPU.md").write_text(
        "---\ntitle: BGE na CPU\n---\nDecisao: colocar CUDA_VISIBLE_DEVICES vazio no drop-in cpu-embeddings.conf.\n")
    (raiz / "Fixes" / (HOJE + "-Drop-in removido.md")).write_text(
        "---\ntitle: Drop-in removido\n---\nO drop-in cpu-embeddings.conf foi removido e o embed_device ficou em cpu.\n")
    (raiz / "Sessions" / (HOJE + "-transcript-abc.md")).write_text("conversa bruta sobre o drop-in")
    velho = time.time() - 30 * 86400
    os.utime(raiz / "Decisions" / "2026-09-02-BGE na CPU.md", (velho, velho))
    cfg = Config(vault_path=str(raiz), vault_folders=["Fixes", "Decisions", "Sessions", "Reference"],
                 recordacao_path=str(tmp_path / "rec.sqlite3"))
    sonho_vault._REGISTRO.clear()
    yield SimpleNamespace(cfg=cfg, raiz=raiz)
    for r in sonho_vault._REGISTRO.values():
        r.fechar()
    sonho_vault._REGISTRO.clear()


def modelo(relacao="updates", confirma=True,
           cb="CUDA_VISIBLE_DEVICES vazio no drop-in cpu-embeddings.conf",
           ca="O drop-in cpu-embeddings.conf foi removido"):
    chamadas = []

    def perguntar(system, prompt):
        chamadas.append(system[:30])
        if system == sonho_vault.CONFIRMACAO:
            return json.dumps({"same_subject": confirma, "a_replaces_or_contradicts_b": confirma})
        return json.dumps({"relation": relacao, "claim_in_B": cb, "claim_in_A": ca, "confidence": 0.9})
    perguntar.chamadas = chamadas
    return perguntar


ORDEM = ["Fixes/" + HOJE + "-Drop-in removido.md", "Sessions/" + HOJE + "-transcript-abc.md",
         "Decisions/2026-09-02-BGE na CPU.md"]


def test_sonho_acha_atualizacao_confirmada(base):
    r = sonho_vault.sonhar(VaultFalso(base.cfg, ORDEM), modelo(), dias=2)
    assert r["notas_recentes"] == 1 and r["pares"] == 1
    assert [(a["a"], a["b"], a["relacao"]) for a in r["achados"]] == [
        ("Fixes/" + HOJE + "-Drop-in removido.md", "Decisions/2026-09-02-BGE na CPU.md", "updates")]


def test_transcricao_nem_e_recente_nem_vizinha(base):
    r = sonho_vault.sonhar(VaultFalso(base.cfg, ORDEM), modelo(), dias=2)
    assert all("transcript" not in x["b"] for x in r["achados"] + r["descartados"])


def test_so_compara_com_nota_mais_antiga(base):
    """A nota antiga nao e recente (mtime de 30 dias), e a recente nao se compara consigo."""
    v = VaultFalso(base.cfg, ORDEM)
    r = sonho_vault.sonhar(v, modelo(), dias=2)
    assert len(v.buscas) == 1 and r["pares"] == 1


def test_confirmacao_negada_vira_descartado(base):
    r = sonho_vault.sonhar(VaultFalso(base.cfg, ORDEM), modelo(confirma=False), dias=2)
    assert r["achados"] == [] and r["descartados"][0]["motivo"] == "nao confirmado na segunda pergunta"


def test_citacao_inventada_nem_chega_a_confirmacao(base):
    p = modelo(cb="o BGE tem que ficar na GPU para sempre")
    r = sonho_vault.sonhar(VaultFalso(base.cfg, ORDEM), p, dias=2)
    assert r["achados"] == [] and "citacao_inventada" in r["descartados"][0]["motivo"]
    assert len(p.chamadas) == 1


def test_complemento_nao_e_achado_nem_descarte(base):
    r = sonho_vault.sonhar(VaultFalso(base.cfg, ORDEM), modelo(relacao="complements"), dias=2)
    assert r["achados"] == [] and r["descartados"] == [] and r["julgados"] == 1


def test_modelo_que_falha_nao_derruba_o_sonho(base):
    def quebra(s, p):
        raise ConnectionError("llama fora")
    r = sonho_vault.sonhar(VaultFalso(base.cfg, ORDEM), quebra, dias=2)
    assert r["julgados"] == 0 and "llama fora" in r["descartados"][0]["motivo"]


def test_sonhar_e_registrar_escreve_a_nota_so_se_houver_o_que_dizer(base):
    v = VaultFalso(base.cfg, ORDEM)
    r = sonho_vault.sonhar_e_registrar(v, dias=2, perguntar=modelo())
    nota = base.raiz / r["nota"]
    texto = nota.read_text()
    assert r["nota"].startswith("Reference/") and "[[" + HOJE + "-Drop-in removido]] updates" in texto
    assert "—" not in texto and "–" not in texto
    r2 = sonho_vault.sonhar_e_registrar(v, dias=2, perguntar=modelo(relacao="complements"))
    assert "nota" not in r2


def test_nota_do_sonho_nao_e_sonhada(base):
    """Pelo caminho que create_note de fato devolve, com prefixo de data."""
    v = VaultFalso(base.cfg, ORDEM)
    caminho = sonho_vault.sonhar_e_registrar(v, dias=2, perguntar=modelo())["nota"]
    assert (base.raiz / caminho).exists()
    assert caminho not in sonho_vault.notas_recentes(base.cfg, 2, 50)


def test_vizinha_mais_nova_nao_e_comparada(base):
    """A nota de 26/09 nao se compara com uma de 27/09: o sonho pergunta se a nova muda a antiga.

    As duas sao recentes pela data do nome. 26/09 compara so com a de 02/09;
    27/09 compara com 26/09 e 02/09. Sao 3 pares; sem a regra seriam 4."""
    (base.raiz / "Fixes" / (AMANHA + "-Mais nova.md")).write_text("---\ntitle: Mais nova\n---\nqualquer coisa\n")
    ordem = ["Fixes/" + AMANHA + "-Mais nova.md"] + ORDEM
    r = sonho_vault.sonhar(VaultFalso(base.cfg, ordem), modelo(relacao="complements"), dias=2)
    assert r["pares"] == 3


def test_confirmacao_exige_mesmo_assunto():
    def p(system, prompt):
        return json.dumps({"same_subject": False, "a_replaces_or_contradicts_b": True})
    v = SimpleNamespace(citacao_a="x", citacao_b="y")
    assert sonho_vault._confirmar(p, v, "a", "b") is False


def test_relatorio_nao_tem_travessao_nem_quando_a_citacao_tem():
    r = {"achados": [{"a": "Fixes/a.md", "b": "Decisions/b.md", "relacao": "updates",
                      "citacao_a": "agora \u2014 depois", "citacao_b": "antes \u2013 durante"}],
         "descartados": [], "lacunas": [], "mais_lembradas": [], "notas_recentes": 1, "pares": 1,
         "julgados": 1, "segundos": 1.0}
    titulo, corpo = sonho_vault.relatorio(r, "2026-09-27")
    assert "\u2014" not in corpo + titulo and "\u2013" not in corpo + titulo
    assert corpo.startswith("---\ngerado_por: sonho\n---")


def test_desligado(base):
    base.cfg.sonho_enabled = False
    assert sonho_vault.sonhar_e_registrar(VaultFalso(base.cfg, ORDEM)) == {"desligado": True}


# ── recordacao no search_vault e ferramentas ────────────────────────────────

def test_search_vault_registra_o_que_devolveu(base, monkeypatch):
    v = VaultFalso(base.cfg, ORDEM)
    monkeypatch.setattr(server, "_vault", v)
    monkeypatch.setattr(server, "_engine", SimpleNamespace(cfg=base.cfg))
    monkeypatch.setattr(base.cfg, "route", lambda **k: "agent", raising=False)
    for q in ("drop-in", "cuda visible devices", "embed_device"):
        asyncio.run(server.search_vault(query=q, limit=3, scope="notes"))
    r = json.loads(server.recall_stats(days=7))
    assert r["totals"]["consultas"] == 3
    # as tres voltaram no topo das tres consultas: empatam, e o desempate e alfabetico
    assert [m["caminho"] for m in r["most_recalled"]] == sorted(ORDEM)


def test_recordacao_que_quebra_nao_derruba_a_busca(base, monkeypatch):
    monkeypatch.setattr(sonho_vault, "registro", lambda cfg: (_ for _ in ()).throw(OSError("disco")))
    sonho_vault.lembrar(base.cfg, "q", [{"path": "a.md"}])


def test_recall_stats_desligado(base, monkeypatch):
    base.cfg.recordacao_enabled = False
    monkeypatch.setattr(server, "_vault", SimpleNamespace(cfg=base.cfg))
    assert json.loads(server.recall_stats())["error_type"] == "disabled"


def test_dream_run_submete_job(base, monkeypatch):
    pedidos = []
    monkeypatch.setattr(server, "_vault", SimpleNamespace(cfg=base.cfg))
    monkeypatch.setattr(server.jobs, "submit", lambda nome, fn, *a, **k: pedidos.append((nome, k)) or "j1")
    r = json.loads(server.dream_run(days=3, write_note=False))
    assert r["job_id"] == "j1" and pedidos == [("sonho", {"dias": 3.0, "escrever_nota": False})]


def test_nota_antiga_tocada_por_passe_em_lote_nao_e_recente(base):
    """O caso real: relink reescreve notas de agosto e o mtime delas vira hoje."""
    p = base.raiz / "Decisions" / "2026-08-01-Antiga relinkada.md"
    p.write_text("---\ntitle: Antiga\n---\nconteudo de agosto\n\n## Related\n- [[x]]\n")
    assert "Decisions/2026-08-01-Antiga relinkada.md" not in sonho_vault.notas_recentes(base.cfg, 2, 50)


def test_data_do_frontmatter_quando_o_nome_nao_tem(base):
    assert sonho_vault.data_da_nota("Tools/x.md", "---\ndate: 2026-08-02\n---\n", time.time()) == "2026-08-02"
    assert sonho_vault.data_da_nota("Tools/2026-09-01-x.md", "---\ndate: 2026-08-02\n---\n", 0) == "2026-09-01"
    hoje = time.strftime("%Y-%m-%d")
    assert sonho_vault.data_da_nota("Tools/x.md", "sem data", time.time()) == hoje


def test_read_note_registra_abertura_ligada_a_busca(base, monkeypatch):
    v = VaultFalso(base.cfg, ORDEM)
    v.find_notes_by_stem = lambda stem: [base.raiz / ORDEM[2]]
    monkeypatch.setattr(server, "_vault", v)
    monkeypatch.setattr(server, "_engine", SimpleNamespace(cfg=base.cfg))
    monkeypatch.setattr(base.cfg, "route", lambda **k: "agent", raising=False)
    asyncio.run(server.search_vault(query="drop-in", limit=3, scope="notes"))
    texto = server.read_note(note_name="BGE na CPU")
    assert "CUDA_VISIBLE_DEVICES" in texto
    r = json.loads(server.recall_stats(days=1))
    assert r["opened_by_rank"] == [{"posicao": 1, "devolvidas": 1, "abertas": 0, "taxa": 0.0},
                                   {"posicao": 2, "devolvidas": 1, "abertas": 0, "taxa": 0.0},
                                   {"posicao": 3, "devolvidas": 1, "abertas": 1, "taxa": 1.0}]
