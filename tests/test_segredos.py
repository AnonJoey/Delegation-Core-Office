"""Pacote segredos, a leitura de log sem segredo, a escrita protegida e a regra do vigia."""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import delegation_core.server as server
from delegation_core import registros, vigia
from delegation_core.segredos import achar, redigir

AMOSTRAS = {
    "anthropic": "sk-ant-api03-" + "a" * 40,
    "openai": "sk-proj-" + "b" * 40,
    "github": "ghp_" + "c" * 36,
    "google": "AIza" + "d" * 35,
    "aws": "AKIA" + "ABCDEFGHIJKLMNOP",
    "slack": "xoxb-" + "1234567890-abcdef",
    "clickup": "pk_12345_" + "ABCDEFGHIJKLMNOPQRSTUV",
    "huggingface": "hf_" + "e" * 34,
    "jwt": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.dGVzdGVzdGVzdGVzdA",
}


@pytest.mark.parametrize("tipo,segredo", list(AMOSTRAS.items()))
def test_cada_tipo_e_achado_e_coberto(tipo, segredo):
    texto, n = redigir(f"antes {segredo} depois")
    assert n == {tipo: 1} and segredo not in texto and texto.startswith("antes [REDIGIDO:") and texto.endswith(" depois")


def test_bearer_cobre_so_o_token():
    texto, n = redigir("Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123")
    assert n == {"bearer": 1} and texto == "Authorization: Bearer [REDIGIDO:bearer:0123]"


def test_senha_em_url_cobre_so_a_senha():
    texto, _ = redigir("postgres://joey:senhaSecreta9@localhost/db")
    assert texto == "postgres://joey:[REDIGIDO:senha_em_url]@localhost/db"


def test_chave_privada_inteira_vira_uma_marca():
    pem = "-----BEGIN OPENSSH PRIVATE KEY-----\nAAAA\nBBBB\n-----END OPENSSH PRIVATE KEY-----"
    texto, n = redigir(f"x\n{pem}\ny")
    assert texto == "x\n[REDIGIDO:chave_privada]\ny" and n == {"chave_privada": 1}


def test_segredo_conhecido_literal():
    tok = "TokenDoDaemonComMaisDe12"
    texto, n = redigir(f"o token {tok} vazou", (tok,))
    assert tok not in texto and n == {"conhecido": 1} and "[REDIGIDO:conhecido:De12]" in texto


def test_texto_comum_nao_e_tocado():
    comum = "sk-curto, eyJ sem pontos, bearer curto, a senha e o que voce escolher, https://site.com/a:b"
    assert redigir(comum) == (comum, {})


def test_nao_redige_duas_vezes():
    """O caso que importa e a senha em URL: a marca cabe no proprio padrao."""
    uma, _ = redigir("x " + AMOSTRAS["github"] + " postgres://joey:senhaSecreta9@localhost/db")
    assert redigir(uma) == (uma, {})


def test_achar_so_conta():
    assert achar(AMOSTRAS["aws"] + " " + AMOSTRAS["aws"]) == {"aws": 2}


# ── leitura de log ──────────────────────────────────────────────────────────

@pytest.fixture
def conf(tmp_path):
    (tmp_path / "server.log").write_text("\n".join([
        "2026-09-27 01:00:00,000 [INFO] HTTP Request: POST http://x \"200\"",
        "2026-09-27 01:00:01,000 [INFO] Processing request of type CallToolRequest",
        "2026-09-27 01:00:02,000 [INFO] Created new transport with session ID: abc",
        "2026-09-27 01:00:03,000 [WARNING] reindex demorou",
        "2026-09-27 01:00:04,000 [ERROR] falhou com Bearer abcdefghijklmnopqrstuvwxyz0123",
        "2026-09-27 01:00:05,000 [INFO] job pronto",
    ]) + "\n")
    return tmp_path


def test_log_tira_ruido_e_cobre_segredo(conf):
    r = registros.ler(conf, "server")
    assert [l[24:] for l in r["linhas"]] == ["[WARNING] reindex demorou",
                                              "[ERROR] falhou com Bearer [REDIGIDO:bearer:0123]",
                                              "[INFO] job pronto"]
    assert r["segredos_cobertos"] == {"bearer": 1}


def test_log_com_ruido_quando_pedido(conf):
    assert len(registros.ler(conf, "server", com_ruido=True)["linhas"]) == 6


def test_log_nivel_minimo_e_filtro(conf):
    assert len(registros.ler(conf, "server", nivel="warning")["linhas"]) == 2
    assert registros.ler(conf, "server", filtro="PRONTO")["linhas"][0].endswith("job pronto")


def test_log_so_as_ultimas(conf):
    assert registros.ler(conf, "server", linhas=1)["linhas"][0].endswith("job pronto")


def test_log_le_so_o_fim_de_arquivo_grande(conf):
    (conf / "llama_cpp.log").write_text("linha velha\n" * 100000 + "a ultima\n")
    r = registros.ler(conf, "llama", max_bytes=1000)
    assert r["linhas"][-1] == "a ultima" and r["lidas_do_fim"] < 200


def test_log_fonte_desconhecida_e_caminho_nao_passam(conf):
    assert "erro" in registros.ler(conf, "../../etc/passwd")
    assert "erro" in registros.ler(conf, "server", filtro="(")


def test_ferramenta_logs(conf, monkeypatch):
    import delegation_core.config as config
    monkeypatch.setattr(config, "CONFIG_DIR", conf)
    monkeypatch.setattr(server, "_vault", SimpleNamespace(cfg=SimpleNamespace(server_token="")))
    r = json.loads(asyncio.run(server.logs(source="server", level="error")))
    assert len(r["linhas"]) == 1 and "[REDIGIDO:bearer" in r["linhas"][0]
    assert json.loads(asyncio.run(server.logs(source="x")))["error_type"] == "invalid_input"


# ── escrita protegida e regra ──────────────────────────────────────────────

class VaultFalso:
    def __init__(self, cfg):
        self.cfg = cfg

    def index_note(self, t, m):
        self.indexado = t
        return True

    def stamp_indexed(self, r):
        pass


def test_create_note_cobre_segredo_e_diz(tmp_path, monkeypatch):
    from delegation_core import notewriter
    from delegation_core.config import Config
    monkeypatch.setattr(notewriter, "post_write_links", lambda *a, **k: None)
    cfg = Config(vault_path=str(tmp_path), vault_folders=["Fixes"])
    (tmp_path / "Fixes").mkdir()
    v = VaultFalso(cfg)
    r = notewriter.create_note(v, "Fixes", "vazou", "o token e " + AMOSTRAS["github"])
    texto = (tmp_path / r["path"]).read_text()
    assert AMOSTRAS["github"] not in texto and AMOSTRAS["github"] not in v.indexado
    assert r["secrets_redacted"] == {"github": 1}
    cfg.redigir_segredos = False
    r2 = notewriter.create_note(v, "Fixes", "vazou de novo", "o token e " + AMOSTRAS["github"])
    assert AMOSTRAS["github"] in (tmp_path / r2["path"]).read_text() and "secrets_redacted" not in r2


def test_regra_segredo_no_vault_so_nas_recentes(tmp_path):
    (tmp_path / "Fixes").mkdir()
    (tmp_path / "Fixes" / "nova.md").write_text("chave " + AMOSTRAS["openai"])
    velha = tmp_path / "Fixes" / "velha.md"
    velha.write_text("chave " + AMOSTRAS["aws"])
    t = time.time() - 5 * 86400
    os.utime(velha, (t, t))
    cfg = SimpleNamespace(vault=tmp_path, vault_folders=["Fixes"], server_token="")
    d = vigia.regra_segredo_no_vault(SimpleNamespace(cfg=cfg))
    assert [x.sujeito for x in d] == ["Fixes/nova.md"] and d[0].detalhe["tipos"] == {"openai": 1}


def test_write_note_diz_ao_agente_o_que_cobriu(tmp_path, monkeypatch):
    """Visto no teste ponta a ponta: a nota saia redigida e a resposta nao dizia."""
    from delegation_core import notewriter
    from delegation_core.config import Config
    monkeypatch.setattr(notewriter, "post_write_links", lambda *a, **k: None)
    cfg = Config(vault_path=str(tmp_path), vault_folders=["Fixes"])
    (tmp_path / "Fixes").mkdir()
    monkeypatch.setattr(server, "_vault", VaultFalso(cfg))
    r = json.loads(server.write_note(folder="Fixes", title="t", content="x " + AMOSTRAS["aws"]))
    assert r["secrets_redacted"] == {"aws": 1}
    r = json.loads(server.write_note(folder="Fixes", title="t2", content="nada secreto"))
    assert "secrets_redacted" not in r
