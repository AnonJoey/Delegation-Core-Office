"""Declarative external-ingestion sources and exclusion patterns."""

from delegation_core.config import Config
from delegation_core.ingest import IngestManager


class FakeVault:
    def __init__(self, cfg):
        self.cfg = cfg
        self.indexed = []

    def index_note(self, content, metadata, doc_id=""):
        self.indexed.append((doc_id, metadata))


def _write(path, text="# document"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_default_patterns_skip_generated_directories(tmp_path, monkeypatch):
    import delegation_core.ingest as ingest_mod

    monkeypatch.setattr(ingest_mod, "_REGISTRY_FILE", tmp_path / "registry.json")
    source = tmp_path / "project"
    _write(source / "docs" / "guide.md")
    _write(source / "build" / "generated.md")

    vault = FakeVault(Config(vault_path=str(tmp_path / "vault")))
    result = IngestManager(vault).ingest(str(source))

    assert result["indexed"] == 1
    assert result["excluded"] == 1
    assert vault.indexed[0][1]["path"].endswith("guide.md")


def test_declared_sources_refuse_an_unconfigured_path(tmp_path, monkeypatch):
    import delegation_core.ingest as ingest_mod

    monkeypatch.setattr(ingest_mod, "_REGISTRY_FILE", tmp_path / "registry.json")
    allowed = tmp_path / "allowed"
    other = tmp_path / "other"
    _write(allowed / "guide.md")
    _write(other / "guide.md")
    cfg = Config(vault_path=str(tmp_path / "vault"), ingest_exclude_patterns=[], ingest_sources=[
        {"name": "allowed-docs", "path": str(allowed), "recursive": True, "enabled": True}
    ])

    result = IngestManager(FakeVault(cfg)).ingest(str(other))

    assert "not configured" in result["error"]


def test_configured_run_uses_name_recursion_and_source_exclusions(tmp_path, monkeypatch):
    import delegation_core.ingest as ingest_mod

    monkeypatch.setattr(ingest_mod, "_REGISTRY_FILE", tmp_path / "registry.json")
    source = tmp_path / "docs"
    _write(source / "keep.md")
    _write(source / "private" / "secret.md")
    _write(source / "nested" / "later.md")
    cfg = Config(vault_path=str(tmp_path / "vault"), ingest_exclude_patterns=[], ingest_sources=[
        {"name": "team-docs", "path": str(source), "recursive": True,
         "enabled": True, "exclude": ["private/*"]}
    ])
    vault = FakeVault(cfg)

    result = IngestManager(vault).ingest_configured("team-docs")

    assert result["configured_count"] == 1
    assert result["indexed"] == 2
    assert result["sources"][0]["excluded"] == 1
    assert result["sources"][0]["name"] == "team-docs"
    assert vault.indexed[0][1]["path"].endswith("keep.md")


def test_configured_run_skips_disabled_sources(tmp_path, monkeypatch):
    import delegation_core.ingest as ingest_mod

    monkeypatch.setattr(ingest_mod, "_REGISTRY_FILE", tmp_path / "registry.json")
    source = tmp_path / "disabled"
    _write(source / "guide.md")
    cfg = Config(vault_path=str(tmp_path / "vault"), ingest_sources=[
        {"name": "disabled-docs", "path": str(source), "enabled": False}
    ])

    result = IngestManager(FakeVault(cfg)).ingest_configured()

    assert result["configured_count"] == 0
    assert result["indexed"] == 0


def test_status_reports_declared_sources_even_before_first_ingest(tmp_path, monkeypatch):
    import delegation_core.ingest as ingest_mod

    monkeypatch.setattr(ingest_mod, "_REGISTRY_FILE", tmp_path / "registry.json")
    source = tmp_path / "planned-docs"
    source.mkdir()
    cfg = Config(vault_path=str(tmp_path / "vault"), ingest_sources=[
        {"name": "planned", "path": str(source), "recursive": False, "enabled": True}
    ])

    status = IngestManager(FakeVault(cfg)).status()

    assert status["count"] == 0
    assert status["configured_source_count"] == 1
    assert status["configured_sources"] == [{
        "name": "planned", "path": str(source.resolve()), "recursive": False,
        "enabled": True, "exists": True,
    }]


def test_one_logical_source_can_ingest_multiple_paths_with_per_path_rules(tmp_path, monkeypatch):
    import delegation_core.ingest as ingest_mod

    monkeypatch.setattr(ingest_mod, "_REGISTRY_FILE", tmp_path / "registry.json")
    docs = tmp_path / "docs"
    root_readme = tmp_path / "README.md"
    _write(docs / "guide.md")
    _write(docs / "drafts" / "private.md")
    _write(root_readme, "# Project")
    cfg = Config(vault_path=str(tmp_path / "vault"), ingest_exclude_patterns=[], ingest_sources=[{
        "name": "project-reference",
        "enabled": True,
        "paths": [
            {"path": str(docs), "recursive": True, "exclude": ["drafts/*"]},
            {"path": str(root_readme), "recursive": False},
        ],
    }])
    vault = FakeVault(cfg)

    result = IngestManager(vault).ingest_configured("project-reference")

    assert result["configured_count"] == 2
    assert result["indexed"] == 2
    assert {item["configured_path"] for item in result["sources"]} == {
        str(docs.resolve()), str(root_readme.resolve()),
    }
    assert all(item["name"] == "project-reference" for item in result["sources"])
    assert all("private.md" not in meta["path"] for _, meta in vault.indexed)


def test_direct_ingest_accepts_each_path_of_a_multiple_path_source(tmp_path, monkeypatch):
    import delegation_core.ingest as ingest_mod

    monkeypatch.setattr(ingest_mod, "_REGISTRY_FILE", tmp_path / "registry.json")
    docs = tmp_path / "docs"
    _write(docs / "guide.md")
    cfg = Config(vault_path=str(tmp_path / "vault"), ingest_exclude_patterns=[], ingest_sources=[{
        "name": "project-reference", "enabled": True,
        "paths": [{"path": str(docs), "recursive": True}],
    }])

    result = IngestManager(FakeVault(cfg)).ingest(str(docs))

    assert result["indexed"] == 1
    assert result["configured_source"] == "project-reference"
