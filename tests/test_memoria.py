"""Memoria: proveniencia, hash esperado, esquecer, corrigir e propostas.

O vault falso reproduz a regra de `find_notes_by_stem` real (substring, sem
caixa), porque e exatamente ela que torna "a primeira que bater" perigosa.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

import delegation_core.server as server
from delegation_core import historico_vault, memoria


class VaultFalso:
    def __init__(self, raiz):
        self.cfg = SimpleNamespace(vault=raiz, vault_folders=["Fixes", "Decisions"], historico_enabled=True,
                                   redigir_segredos=True)
        self.indexadas, self.apagadas = [], []

    def index_note(self, texto, meta):
        self.indexadas.append(meta["path"])
        return True

    def stamp_indexed(self, rels):
        pass

    def delete_notes(self, rels):
        self.apagadas.extend(rels)
        return len(rels)

    def find_notes_by_stem(self, nome):
        saida = []
        for pasta in self.cfg.vault_folders:
            for f in sorted((self.cfg.vault / pasta).rglob("*.md")):
                if nome.lower() in f.name[:-3].lower():
                    saida.append(f)
        return saida


@pytest.fixture
def vault(tmp_path, monkeypatch):
    raiz = tmp_path / "vault"
    (raiz / "Fixes").mkdir(parents=True)
    (raiz / "Decisions").mkdir()
    (raiz / "Fixes" / "deploy.md").write_text("# deploy\nporta 8080\n")
    (raiz / "Fixes" / "deploy-antigo.md").write_text("# antigo\n")
    (raiz / "Decisions" / "unica.md").write_text("# unica\nvalor A\nvalor B\n")
    historico_vault._INSTANCIAS.clear()
    v = VaultFalso(raiz)
    monkeypatch.setattr(server, "_vault", v)
    monkeypatch.setattr(server, "_post_write_links", lambda *a, **k: None)
    yield v
    for h in historico_vault._INSTANCIAS.values():
        h.fechar()
    historico_vault._INSTANCIAS.clear()


def chama(f, **kw):
    r = f(**kw)
    return json.loads(asyncio.run(r) if asyncio.iscoroutine(r) else r)


def test_resolver_exige_nota_unica(vault):
    p, erro = memoria.resolver_unica(vault, "deploy")
    assert erro is None and p.name == "deploy.md", "nome exato vence o parcial"
    p, erro = memoria.resolver_unica(vault, "dep")
    assert p is None and len(erro["candidates"]) == 2
    p, _ = memoria.resolver_unica(vault, "Fixes/deploy-antigo.md")
    assert p.name == "deploy-antigo.md"
    assert memoria.resolver_unica(vault, "../fora.md")[0] is None


def test_hash_e_conflito_no_update(vault):
    h = chama(server.vault_note_hash, note="unica")["hash"]
    r = chama(server.vault_update_note, note_name="unica", append_content="mais", expected_hash=h)
    assert r["status"] == "ok" and r["hash"] != h
    r = chama(server.vault_update_note, note_name="unica", append_content="de novo", expected_hash=h)
    assert "conflict" in json.dumps(r) and r["current_hash"] != h
    assert (vault.cfg.vault / "Decisions" / "unica.md").read_text().count("mais") == 1


def test_update_com_hash_grava_na_nota_certa(vault):
    """Sem hash, update_note pega a primeira que CONTEM o nome; com hash, a resolvida."""
    h = chama(server.vault_note_hash, note="Fixes/deploy-antigo.md")["hash"]
    r = chama(server.vault_update_note, note_name="Fixes/deploy-antigo.md", append_content="X", expected_hash=h)
    assert r["path"] == "Fixes/deploy-antigo.md"
    assert "X" not in (vault.cfg.vault / "Fixes" / "deploy.md").read_text()


def test_esquecer_move_tira_do_indice_e_volta(vault):
    r = chama(server.vault_forget_note, note="unica", reason="obsoleta")
    assert r["status"] == "ok" and vault.apagadas == ["Decisions/unica.md"]
    assert not (vault.cfg.vault / "Decisions" / "unica.md").exists()
    assert (vault.cfg.vault / r["trash"]).read_text().startswith("# unica")
    reg = (vault.cfg.vault / ".lixeira" / "registro.jsonl").read_text()
    assert "obsoleta" in reg
    from delegation_core.historico_vault import restaurar
    assert restaurar(vault, "Decisions/unica.md", 1).get("recreated")
    assert (vault.cfg.vault / "Decisions" / "unica.md").read_text().startswith("# unica")


def test_esquecer_recusa_ambiguo(vault):
    r = chama(server.vault_forget_note, note="dep")
    assert "matches 2 notes" in json.dumps(r) and vault.apagadas == []


def test_corrigir(vault):
    r = chama(server.vault_correct_note, note="deploy", old_text="porta 8080", new_text="porta 9090",
              reason="mudou no PR 5")
    assert r["status"] == "ok"
    texto = (vault.cfg.vault / "Fixes" / "deploy.md").read_text()
    assert "porta 9090" in texto and "8080" not in texto and "mudou no PR 5" in texto
    r = chama(server.vault_correct_note, note="unica", old_text="valor", new_text="x")
    assert "2 times" in json.dumps(r)
    r = chama(server.vault_correct_note, note="unica", old_text="valor A", new_text="x", expected_hash="0" * 16)
    assert "conflict" in json.dumps(r)


def test_propostas_ciclo(vault):
    p = chama(server.vault_propose_edit, note="unica", new_text="valor C", old_text="valor B", reason="r")
    assert p["status"] == "pending" and p["kind"] == "replace"
    assert "valor C" not in (vault.cfg.vault / "Decisions" / "unica.md").read_text(), "propor nao muda nada"
    assert chama(server.vault_proposals)["count"] == 1
    ps = memoria.propostas()
    assert ps.aplicar(vault.cfg, p["id"])["status"] == "ok"
    assert "valor C" in (vault.cfg.vault / "Decisions" / "unica.md").read_text()
    assert "applied" in ps.aplicar(vault.cfg, p["id"])["error"]

    q = ps.propor(vault, "deploy", "nota final")
    (vault.cfg.vault / "Fixes" / "deploy.md").write_text("mudou por fora\n")
    assert "stale" in ps.aplicar(vault.cfg, q["id"])["error"]
    assert ps.listar("stale")[0]["id"] == q["id"]

    s = ps.propor(vault, "deploy", "rodape")
    assert ps.rejeitar(s["id"][:9])["status"] == "rejected"
    assert ps.aplicar(vault.cfg, s["id"])["error"].endswith("rejected")


def test_proposta_aplicada_cobre_segredo(vault):
    ps = memoria.propostas()
    p = ps.propor(vault, "unica", "chave sk-ant-api03-" + "Z" * 90)
    ps.aplicar(vault.cfg, p["id"])
    assert "ZZZZZZZZZZZZ" not in (vault.cfg.vault / "Decisions" / "unica.md").read_text()


def test_proveniencia_no_frontmatter(vault, monkeypatch):
    from delegation_core.notes import compose_note
    t = compose_note("T", "corpo", "2026-10-05", extras=(("written_by", '"codex"'),))
    assert 'written_by: "codex"' in t.split("---")[1]
    t = compose_note("T", "---\nwritten_by: humano\n---\ncorpo", "2026-10-05", extras=(("written_by", '"codex"'),))
    assert t.count("written_by") == 1 and "humano" in t, "o que o autor escreveu vence"
