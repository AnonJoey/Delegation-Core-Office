"""As checagens do doctor para os sistemas do enriquecimento."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from delegation_core import busca_hibrida, doctor_enriquecimento as de
from delegation_core.imagens import leitura

REAL = de.check_busca_hibrida


def _cfg(tmp_path, **kw):
    base = dict(vault=tmp_path, busca_hibrida=True, busca_reordenar=True, busca_reordenador_modelo="",
                busca_reordenador_dispositivo="auto", agenda_enabled=True, historico_enabled=True)
    base.update(kw)
    return SimpleNamespace(**base)


# ── busca hibrida: o daemon manda, a previsao local e so fallback ───────────

def test_daemon_com_reordenador_carregado_e_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(de, "_situacao_no_daemon",
                        lambda c: {"reordenador_carregado": True, "notas_no_indice_lexico": 500})
    r = de.check_busca_hibrida(_cfg(tmp_path))
    assert r["status"] == "ok" and r["detail"].startswith("daemon:")


def test_daemon_diz_por_que_ficou_densa(tmp_path, monkeypatch):
    monkeypatch.setattr(de, "_situacao_no_daemon",
                        lambda c: {"reordenador_carregado": False, "motivo_sem_reordenador": "sem 1,5 GB livres"})
    r = de.check_busca_hibrida(_cfg(tmp_path))
    assert r["status"] == "warn" and "sem 1,5 GB" in r["detail"]


def test_sem_daemon_preve_localmente_e_diz_que_e_previsao(tmp_path, monkeypatch):
    monkeypatch.setattr(de, "_situacao_no_daemon", lambda c: None)
    monkeypatch.setattr(busca_hibrida, "_modelo_no_cache", lambda m: True)
    monkeypatch.setattr(busca_hibrida, "_gpu_livre_mb", lambda: 4000)
    r = de.check_busca_hibrida(_cfg(tmp_path))
    assert r["status"] == "ok" and r["detail"].startswith("predicted from this process")
    monkeypatch.setattr(busca_hibrida, "_gpu_livre_mb", lambda: 500)
    assert de.check_busca_hibrida(_cfg(tmp_path))["status"] == "warn"


def test_modelo_ausente_da_o_comando(tmp_path, monkeypatch):
    monkeypatch.setattr(de, "_situacao_no_daemon", lambda c: None)
    monkeypatch.setattr(busca_hibrida, "_modelo_no_cache", lambda m: False)
    r = de.check_busca_hibrida(_cfg(tmp_path))
    assert r["status"] == "warn" and "snapshot_download" in r["fix"]


def test_desligada_e_skip(tmp_path):
    assert de.check_busca_hibrida(_cfg(tmp_path, busca_hibrida=False))["status"] == "skip"


# ── ocr ────────────────────────────────────────────────────────────────────

def test_ocr(monkeypatch):
    import delegation_core.imagens as im
    monkeypatch.setattr(de.shutil, "which", lambda n: None)
    assert de.check_ocr()["status"] == "warn"
    monkeypatch.setattr(de.shutil, "which", lambda n: "/usr/bin/tesseract")
    monkeypatch.setattr(im, "idiomas_disponiveis", lambda t=None: ["osd"])
    r = de.check_ocr()
    assert r["status"] == "warn" and r["fix"] == "delegation-core ocr-setup"
    monkeypatch.setattr(im, "idiomas_disponiveis", lambda t=None: ["osd", "por", "eng"])
    assert de.check_ocr() == {"check": "ocr", "status": "ok", "detail": "tesseract with eng, por"}


# ── agenda, alertas, historico ─────────────────────────────────────────────

def test_agenda(tmp_path):
    cfg = _cfg(tmp_path)
    assert de.check_agenda(cfg, tmp_path)["status"] == "warn"
    (tmp_path / "agenda.json").write_text(json.dumps({"a": {"execucoes": 3}, "b": {}}))
    assert de.check_agenda(cfg, tmp_path) == {"check": "scheduler", "status": "ok",
                                              "detail": "2 task(s), 1 have run, none failing"}
    (tmp_path / "agenda.json").write_text(json.dumps({"a": {"falhas_seguidas": 2, "ultimo_erro": "OSError: x"}}))
    r = de.check_agenda(cfg, tmp_path)
    assert r["status"] == "error" and "OSError" in r["detail"]
    (tmp_path / "agenda.json").write_text("{quebrado")
    assert de.check_agenda(cfg, tmp_path)["status"] == "warn"
    assert de.check_agenda(_cfg(tmp_path, agenda_enabled=False), tmp_path)["status"] == "skip"


def test_alertas(tmp_path):
    assert de.check_alertas(tmp_path)["status"] == "ok"
    (tmp_path / "alertas.json").write_text(json.dumps({"alertas": {
        "x": {"estado": "disparando", "severidade": "aviso", "mensagem": "12 links quebrados"},
        "y": {"estado": "pendente", "severidade": "critico", "mensagem": "ainda nao"}}}))
    r = de.check_alertas(tmp_path)
    assert r["status"] == "warn" and r["detail"] == "12 links quebrados"
    (tmp_path / "alertas.json").write_text(json.dumps({"alertas": {
        "z": {"estado": "disparando", "severidade": "critico", "mensagem": "disco"}}}))
    assert de.check_alertas(tmp_path)["status"] == "error"


def test_historico(tmp_path):
    cfg = _cfg(tmp_path)
    assert "no snapshot" in de.check_historico(cfg)["detail"]
    (tmp_path / ".historico" / "objetos" / "ab").mkdir(parents=True)
    (tmp_path / ".historico" / "objetos" / "ab" / "cd").write_bytes(b"x" * 2_000_000)
    r = de.check_historico(cfg)
    assert r["status"] == "ok" and r["detail"].startswith("2 MB")


def test_doctor_inclui_as_checagens_novas_e_sobrevive_a_quebra(tmp_path, monkeypatch):
    from delegation_core import doctor
    monkeypatch.setattr(de, "todas", lambda cfg: [{"check": "x", "status": "ok", "detail": "d"}])
    nomes = [c["check"] for c in doctor.run_all(doctor_cfg(tmp_path))["checks"]]
    assert "x" in nomes
    monkeypatch.setattr(de, "todas", lambda cfg: (_ for _ in ()).throw(RuntimeError("quebrou")))
    r = doctor.run_all(doctor_cfg(tmp_path))
    assert any(c["check"] == "enrichment_checks" and "quebrou" in c["detail"] for c in r["checks"])


def doctor_cfg(tmp_path):
    from delegation_core.config import Config
    return Config(vault_path=str(tmp_path), vault_folders=["Fixes"])


def test_fatos(tmp_path, monkeypatch):
    from delegation_core import fatos_vault
    raiz = tmp_path / "v"
    (raiz / "Fixes").mkdir(parents=True)
    for i in range(3):
        (raiz / "Fixes" / f"n{i}.md").write_text(f"nota {i}")
    cfg = SimpleNamespace(vault=raiz, fatos_enabled=True, fatos_path=str(tmp_path / "f.sqlite3"))
    fatos_vault._ARMAZEM.clear()
    r = de.check_fatos(cfg)
    assert r["status"] == "ok" and "3 note(s) pending" in r["detail"]
    for i in range(130):
        (raiz / "Fixes" / f"m{i}.md").write_text(f"outra {i}")
    r = de.check_fatos(cfg)
    assert r["status"] == "warn" and "fatos-noturno" in r["fix"]
    fatos_vault._ARMAZEM.clear()
    assert de.check_fatos(SimpleNamespace(fatos_enabled=False))["status"] == "skip"


def test_atencao(tmp_path):
    import json
    assert de.check_atencao(tmp_path)["status"] == "ok"
    (tmp_path / "atencao.json").write_text(json.dumps({"gerado_em": 1000.0, "itens": [{}, {}], "erros": {}}))
    assert de.check_atencao(tmp_path, agora=1000.0 + 600)["status"] == "ok"
    r = de.check_atencao(tmp_path, agora=1000.0 + 7200)
    assert r["status"] == "warn" and "hour" in r["fix"]
    (tmp_path / "atencao.json").write_text(json.dumps({"gerado_em": 1000.0, "itens": [], "erros": {"fatos": "x"}}))
    assert "fatos" in de.check_atencao(tmp_path, agora=1001.0)["detail"]
    (tmp_path / "atencao.json").write_text("{quebrado")
    assert de.check_atencao(tmp_path)["status"] == "warn"


def test_codigo(tmp_path):
    import json
    from delegation_core import codigo_vault
    gd = tmp_path / "graphs" / "g"
    gd.mkdir(parents=True)
    (gd / "graph.json").write_text(json.dumps({"nodes": []}))
    cfg = SimpleNamespace(codigo_enabled=True, graphs_dir=tmp_path / "graphs", codigo_path=str(tmp_path / "c.sqlite3"))
    codigo_vault._INDICE.clear()
    assert "1 of 1 graph(s) indexed" in de.check_codigo(cfg)["detail"]
    cfg.graphs_dir = tmp_path / "nada"
    assert de.check_codigo(cfg)["detail"] == "no code graph built"
    codigo_vault._INDICE.clear()


# ── integridade do banco do historico ───────────────────────────────────────

def _banco_do_historico(tmp_path, linhas=3000):
    import sqlite3
    raiz = tmp_path / ".historico"
    (raiz / "objetos").mkdir(parents=True)
    con = sqlite3.connect(raiz / "versoes.sqlite3")
    con.execute("PRAGMA journal_mode=DELETE")
    con.execute("CREATE TABLE versoes (id INTEGER PRIMARY KEY AUTOINCREMENT, caminho TEXT, sha TEXT)")
    con.executemany("INSERT INTO versoes(caminho, sha) VALUES (?, ?)",
                    [(f"Reference/nota-{i}.md", "a" * 40) for i in range(linhas)])
    con.commit()
    con.close()
    return raiz / "versoes.sqlite3"


def test_historico_com_banco_sao_continua_ok(tmp_path):
    _banco_do_historico(tmp_path)
    r = de.check_historico(_cfg(tmp_path))
    assert r["status"] == "ok" and "integrity ok" in r["detail"]


def test_historico_com_banco_corrompido_e_erro_e_diz_o_que_fazer(tmp_path):
    """O agendador falhou 166 vezes seguidas com 'database disk image is malformed' sem que o doctor
    dissesse onde: o banco do historico foi corrompido por um sync que levava o arquivo vivo (e o
    -wal) de uma maquina para outra. O doctor so media o tamanho dos objetos."""
    banco = _banco_do_historico(tmp_path)
    dados = bytearray(banco.read_bytes())
    for i in range(8192, 40960, 7):          # estraga paginas do meio, deixa o cabecalho
        dados[i] = (dados[i] + 1) % 256
    banco.write_bytes(bytes(dados))
    r = de.check_historico(_cfg(tmp_path))
    assert r["status"] == "error"
    assert "malformed" in r["detail"] or "integrity" in r["detail"]
    assert "sqlite3" in r["fix"] and ".recover" in r["fix"] and "sync" in r["fix"]


def test_historico_nao_cria_arquivos_ao_checar(tmp_path):
    """Abrir o banco de um daemon vivo em modo somente leitura nao pode deixar -wal ou -shm."""
    banco = _banco_do_historico(tmp_path)
    antes = sorted(p.name for p in banco.parent.iterdir())
    de.check_historico(_cfg(tmp_path))
    assert sorted(p.name for p in banco.parent.iterdir()) == antes
