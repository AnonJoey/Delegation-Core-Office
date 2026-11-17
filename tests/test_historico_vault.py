"""A ligacao do historico ao vault e ao servidor.

O armazem tem teste proprio (test_historico.py). Aqui: o antes e depois dos
passes em lote, a protecao que nunca derruba a operacao, o rename levando o
historico junto, a restauracao reversivel, e as tres ferramentas MCP.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

import delegation_core.server as server
from delegation_core import historico_vault


class VaultFalso:
    def __init__(self, raiz, pastas=("Fixes", "Decisions")):
        self.cfg = SimpleNamespace(vault=raiz, vault_folders=list(pastas), historico_enabled=True)
        self.indexadas, self.carimbadas = [], []

    def index_note(self, texto, meta):
        self.indexadas.append(meta["path"])
        return True

    def stamp_indexed(self, rels):
        self.carimbadas.extend(rels)

    def find_notes_by_stem(self, stem):
        return sorted(self.cfg.vault.rglob(f"{stem}.md"))


@pytest.fixture
def vault(tmp_path, monkeypatch):
    raiz = tmp_path / "vault"
    (raiz / "Fixes").mkdir(parents=True)
    (raiz / "Decisions").mkdir()
    (raiz / "Fixes" / "a.md").write_text("versao original\n")
    (raiz / "Fixes" / ".obsidian").mkdir()
    (raiz / "Fixes" / ".obsidian" / "ignorar.md").write_text("nao e nota")
    historico_vault._INSTANCIAS.clear()
    v = VaultFalso(raiz)
    monkeypatch.setattr(server, "_vault", v)
    yield v
    for h in historico_vault._INSTANCIAS.values():
        h.fechar()
    historico_vault._INSTANCIAS.clear()


def _chamar(f, **kw):
    r = f(**kw)
    return json.loads(asyncio.run(r) if asyncio.iscoroutine(r) else r)


def test_notas_do_vault_pula_diretorio_oculto(vault):
    assert historico_vault.notas_do_vault(vault.cfg) == ["Fixes/a.md"]


def test_sob_historico_guarda_o_antes_e_marca_o_depois(vault):
    with historico_vault.sob_historico(vault.cfg, "relink_folder Fixes"):
        (vault.cfg.vault / "Fixes" / "a.md").write_text("versao original\n\n## Related\n- [[b]]\n")
    vs = historico_vault.abrir(vault.cfg).versoes("Fixes/a.md")
    assert [v["origem"] for v in vs] == ["relink_folder Fixes", "antes de relink_folder Fixes"]


def test_falha_do_historico_nao_derruba_a_operacao(vault, monkeypatch):
    def quebra(*a, **k):
        raise OSError("disco cheio")
    monkeypatch.setattr(historico_vault, "fotografar", quebra)
    feito = []
    with historico_vault.sob_historico(vault.cfg, "x"):
        feito.append(1)
    assert feito == [1]


def test_falha_da_operacao_propaga_e_o_depois_ainda_roda(vault):
    with pytest.raises(ValueError):
        with historico_vault.sob_historico(vault.cfg, "op"):
            (vault.cfg.vault / "Fixes" / "a.md").write_text("meio escrito")
            raise ValueError("a operacao quebrou")
    assert historico_vault.abrir(vault.cfg).texto("Fixes/a.md") == "meio escrito"


def test_desligado_nao_cria_nada(vault):
    vault.cfg.historico_enabled = False
    assert historico_vault.abrir(vault.cfg) is None and historico_vault.fotografar(vault.cfg) is None
    assert not (vault.cfg.vault / ".historico").exists()


def test_restaurar_e_reversivel(vault):
    nota = vault.cfg.vault / "Fixes" / "a.md"
    historico_vault.fotografar(vault.cfg)
    nota.write_text("estragada pelo passe\n")
    historico_vault.fotografar(vault.cfg, origem="relink")
    r = historico_vault.restaurar(vault, "Fixes/a.md", 2)
    assert r["status"] == "ok" and nota.read_text() == "versao original\n"
    assert "Fixes/a.md" in vault.indexadas and "Fixes/a.md" in vault.carimbadas
    # desfazer: a versao "estragada" foi guardada antes e esta na posicao 2
    historico_vault.restaurar(vault, "Fixes/a.md", 2)
    assert nota.read_text() == "estragada pelo passe\n"


def test_restaurar_nota_apagada_recria(vault):
    historico_vault.fotografar(vault.cfg)
    (vault.cfg.vault / "Fixes" / "a.md").unlink()
    r = historico_vault.restaurar(vault, "Fixes/a.md", 1)
    assert r["recreated"] and (vault.cfg.vault / "Fixes" / "a.md").read_text() == "versao original\n"
    assert vault.indexadas == ["Fixes/a.md"] and vault.carimbadas == ["Fixes/a.md"]


def test_restaurar_versao_inexistente(vault):
    historico_vault.fotografar(vault.cfg)
    assert "not found" in historico_vault.restaurar(vault, "Fixes/a.md", 9)["error"]


# ── ferramentas MCP e a ligacao nos passes ──────────────────────────────────

def test_ferramentas_history_diff_restore(vault):
    nota = vault.cfg.vault / "Fixes" / "a.md"
    historico_vault.fotografar(vault.cfg)
    nota.write_text("versao nova\n")
    historico_vault.fotografar(vault.cfg, origem="relink")
    h = _chamar(server.vault_note_history, note="a")
    assert h["path"] == "Fixes/a.md" and [v["origem"] for v in h["versions"]] == ["relink", "varredura"]
    d = _chamar(server.vault_note_diff, note="Fixes/a.md")
    assert "-versao original" in d["diff"] and "+versao nova" in d["diff"]
    r = _chamar(server.vault_note_restore, note="a", version=2)
    assert r["status"] == "ok" and nota.read_text() == "versao original\n"


def test_ferramentas_erros_tipados(vault):
    assert _chamar(server.vault_note_history, note="nao-existe")["error_type"] == "not_found"
    historico_vault.fotografar(vault.cfg)
    assert _chamar(server.vault_note_diff, note="a")["error_type"] == "not_found"
    assert _chamar(server.vault_note_restore, note="a", version=5)["error_type"] == "not_found"
    vault.cfg.historico_enabled = False
    historico_vault._INSTANCIAS.clear()
    assert _chamar(server.vault_note_history, note="a")["error_type"] == "disabled"


def test_historico_de_nota_apagada_pelo_caminho(vault):
    historico_vault.fotografar(vault.cfg)
    (vault.cfg.vault / "Fixes" / "a.md").unlink()
    assert len(_chamar(server.vault_note_history, note="Fixes/a.md")["versions"]) == 1


def test_relink_passa_pelo_historico(vault, monkeypatch):
    def relink_falso(v, folder, **kw):
        (v.cfg.vault / folder / "a.md").write_text("com Related\n")
        return {"relinked": 1}
    monkeypatch.setattr(server, "_relink_folder", relink_falso)
    assert server._relink_com_historico(vault, "Fixes") == {"relinked": 1}
    origens = [v["origem"] for v in historico_vault.abrir(vault.cfg).versoes("Fixes/a.md")]
    assert origens == ["relink_folder Fixes", "antes de relink_folder Fixes"]


def test_rename_leva_o_historico_para_o_caminho_novo(vault, monkeypatch):
    historico_vault.fotografar(vault.cfg)

    def rename_falso(v, path, new_title):
        (v.cfg.vault / path).rename(v.cfg.vault / "Fixes" / "b.md")
        return {"status": "ok", "path": "Fixes/b.md", "previous_path": path}
    monkeypatch.setattr(server._notewriter, "rename_note", rename_falso)
    _chamar(server.vault_rename_note, path="Fixes/a.md", new_title="b")
    h = historico_vault.abrir(vault.cfg)
    assert h.versoes("Fixes/a.md") == [] and h.texto("Fixes/b.md") == "versao original\n"


def test_manutencao_passa_pelo_historico(vault, monkeypatch):
    class MotorFalso:
        def __init__(self, cfg):
            pass

        async def aclose(self):
            pass

    async def ciclo(engine, v):
        (v.cfg.vault / "Fixes" / "a.md").write_text("mesclada\n")
        return {"merged": 1}
    monkeypatch.setattr(server, "DelegationEngine", MotorFalso)
    monkeypatch.setattr(server, "_engine", SimpleNamespace(cfg=vault.cfg))
    monkeypatch.setattr(server, "_full_maintenance_cycle", ciclo)
    assert asyncio.run(server._bg_maintenance_wrapper()) == {"merged": 1}
    assert historico_vault.abrir(vault.cfg).versoes("Fixes/a.md")[0]["origem"] == "run_maintenance"


def test_restaurar_guarda_a_edicao_que_nenhuma_varredura_viu(vault):
    """O texto atual pode nunca ter sido fotografado: foi escrito depois da
    ultima varredura. Restaurar sem guardar antes o perderia para sempre."""
    nota = vault.cfg.vault / "Fixes" / "a.md"
    historico_vault.fotografar(vault.cfg)
    nota.write_text("edicao que ninguem fotografou\n")
    historico_vault.restaurar(vault, "Fixes/a.md", 1)
    textos = [historico_vault.abrir(vault.cfg).texto("Fixes/a.md", n) for n in (1, 2, 3)]
    assert "edicao que ninguem fotografou\n" in textos
