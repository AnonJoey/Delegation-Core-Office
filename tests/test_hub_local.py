"""O huggingface_hub nao consulta o Hub por conta propria (hub_local.py)."""
from __future__ import annotations

import sys
import types

from delegation_core import hub_local


def test_desliga_por_padrao_e_alcanca_o_modulo_ja_importado(monkeypatch):
    monkeypatch.delenv("HF_HUB_DISABLE_TELEMETRY", raising=False)
    falso = types.SimpleNamespace(HF_HUB_DISABLE_TELEMETRY=False)
    monkeypatch.setitem(sys.modules, "huggingface_hub.constants", falso)
    assert hub_local.sem_telemetria() is True
    assert falso.HF_HUB_DISABLE_TELEMETRY is True
    import os
    assert os.environ["HF_HUB_DISABLE_TELEMETRY"] == "1"


def test_a_escolha_do_operador_vence(monkeypatch):
    monkeypatch.setenv("HF_HUB_DISABLE_TELEMETRY", "0")
    falso = types.SimpleNamespace(HF_HUB_DISABLE_TELEMETRY=False)
    monkeypatch.setitem(sys.modules, "huggingface_hub.constants", falso)
    assert hub_local.sem_telemetria() is False
    assert falso.HF_HUB_DISABLE_TELEMETRY is False


def test_sem_a_biblioteca_importada_so_a_variavel_muda(monkeypatch):
    monkeypatch.delenv("HF_HUB_DISABLE_TELEMETRY", raising=False)
    monkeypatch.delitem(sys.modules, "huggingface_hub.constants", raising=False)
    assert hub_local.sem_telemetria() is True


def test_o_cli_desliga_na_partida():
    """Mesma forma do teste do fastmcp: a chamada esta no `main`, antes de qualquer comando."""
    from pathlib import Path
    fonte = (Path(hub_local.__file__).parent / "cli.py").read_text(encoding="utf-8")
    assert "sem_telemetria()" in fonte
