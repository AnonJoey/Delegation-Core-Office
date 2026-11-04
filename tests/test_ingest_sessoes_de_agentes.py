"""ingest: transcricoes brutas de agentes nao entram no indice por engano.

Relato do Mac de um colega em 2026-11-04: 1.824 trechos da pasta de sessoes do
Claude Code estavam no indice e um arquivo de configuracao de sessao apareceu
como primeiro resultado de busca. Essas transcricoes ja chegam ao vault pelo
hook de fim de sessao, em `Sessions/`; ingeri-las de novo como fonte externa
duplica o conteudo e enche a busca de ruido.

Quem declara a pasta em `ingest_sources` quer o conteudo, e a declaracao vence.
"""

import pytest

from delegation_core.config import Config
from delegation_core.ingest import IngestManager, raizes_de_sessao_de_agentes


class _Colecao:
    def get(self, where=None, include=None):
        return {"ids": [], "metadatas": []}

    def delete(self, ids):
        pass


class _Vault:
    def __init__(self, cfg):
        self.cfg = cfg
        self.indexed = []
        self.collection = _Colecao()

    def index_note(self, content, metadata, doc_id=""):
        self.indexed.append(metadata)

    def _ensure_ready(self):
        pass


@pytest.fixture
def casa(monkeypatch, tmp_path):
    import delegation_core.config as config_mod
    import delegation_core.ingest as ingest_mod
    home = tmp_path / "home"
    (home / ".claude" / "projects" / "-home-x").mkdir(parents=True)
    (home / ".claude" / "projects" / "-home-x" / "s1.md").write_text("sessao bruta", encoding="utf-8")
    (home / ".codex" / "sessions").mkdir(parents=True)
    (home / ".codex" / "sessions" / "r1.md").write_text("rollout bruto", encoding="utf-8")
    (home / "Documents").mkdir()
    (home / "Documents" / "plano.md").write_text("# plano real", encoding="utf-8")
    monkeypatch.setattr(ingest_mod.Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(config_mod, "CONFIG_DIR", tmp_path / "cfg")
    monkeypatch.setattr(ingest_mod, "_REGISTRY_FILE", tmp_path / "cfg" / "ingested_sources.json")
    (tmp_path / "cfg").mkdir()
    return home


def _cfg(tmp_path, **extra):
    return Config(vault_path=str(tmp_path / "vault"), **extra)


def test_as_raizes_conhecidas_sao_as_pastas_de_claude_code_e_codex(casa):
    nomes = {r.as_posix() for r in raizes_de_sessao_de_agentes()}
    assert nomes == {(casa / ".claude" / "projects").as_posix(),
                     (casa / ".codex" / "sessions").as_posix()}


def test_apontar_para_dentro_da_pasta_de_sessoes_e_recusado(casa, tmp_path):
    alvo = casa / ".claude" / "projects" / "-home-x"
    r = IngestManager(_Vault(_cfg(tmp_path))).ingest(str(alvo))
    assert "error" in r
    assert "Sessions" in r["error"] and "ingest_sources" in r["error"]


def test_apontar_para_a_home_pula_as_sessoes_e_indexa_o_resto(casa, tmp_path):
    vault = _Vault(_cfg(tmp_path))
    r = IngestManager(vault).ingest(str(casa))
    assert r["indexed"] == 1, r
    assert not any("s1" in str(m) or "r1" in str(m) for m in vault.indexed)
    assert sorted(r["skipped_agent_sessions"]) == sorted(
        [str(casa / ".claude" / "projects"), str(casa / ".codex" / "sessions")])


def test_fonte_declarada_em_ingest_sources_vence_a_regra(casa, tmp_path):
    alvo = casa / ".claude" / "projects" / "-home-x"
    cfg = _cfg(tmp_path, ingest_sources=[{"name": "sessoes", "path": str(alvo)}])
    r = IngestManager(_Vault(cfg)).ingest(str(alvo))
    assert "error" not in r, r
    assert r["indexed"] == 1
