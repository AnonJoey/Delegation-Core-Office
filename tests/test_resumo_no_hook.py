"""O hook de inicio de sessao usa o resumo em niveis quando a config pede, e o antigo quando nao."""

from __future__ import annotations

import json
import os
import time

import pytest

from delegation_core.hooks import session_start_brief as hook


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    (vault / "Decisions").mkdir(parents=True)
    nota = vault / "Decisions" / "a.md"
    nota.write_text("---\nsummary: Usar sqlite para o indice.\n---\n\ncorpo\n", encoding="utf-8")
    cfg = {"vault_path": str(vault), "vault_folders": ["Decisions"]}
    cfg_arq = tmp_path / "config.json"
    estado = tmp_path / "last_brief.json"
    estado.write_text(json.dumps({"last_check": time.time() - 3600}))
    monkeypatch.setattr(hook, "CONFIG_PATH", cfg_arq)
    monkeypatch.setattr(hook, "STATE_PATH", estado)
    monkeypatch.setattr(hook, "ATENCAO_PATH", tmp_path / "atencao.json")
    monkeypatch.setattr(hook, "_trigger_reindex", lambda: False)
    monkeypatch.setattr(hook, "_trigger_maintenance", lambda: False)
    os.utime(nota, (time.time(), time.time()))

    def escrever(**extra):
        cfg_arq.write_text(json.dumps({**cfg, **extra}))

    return escrever


def test_padrao_lista_so_o_caminho(ambiente, capsys):
    ambiente()
    hook.main()
    saida = capsys.readouterr().out
    assert "`Decisions/a.md`" in saida and "Usar sqlite" not in saida


def test_com_a_flag_mostra_o_trecho_dentro_da_cerca(ambiente, capsys):
    ambiente(resumo_niveis_enabled=True)
    hook.main()
    saida = capsys.readouterr().out
    assert "`Decisions/a.md`" in saida and "> Usar sqlite para o indice." in saida
    assert "untrusted-history:start" in saida and "## Vault activity since your last supported-client session" in saida


def test_falha_do_resumo_cai_no_antigo(ambiente, capsys, monkeypatch):
    ambiente(resumo_niveis_enabled=True)
    from delegation_core import resumo_vault

    monkeypatch.setattr(resumo_vault, "renderizar", lambda *a, **k: 1 / 0)
    hook.main()
    assert "`Decisions/a.md`" in capsys.readouterr().out
