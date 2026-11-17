"""Os dois passos de passagem de bastao nos hooks de sessao: inicio e fim.

Fino de proposito: le o JSON do hook e a config da maquina, e entrega a `passagem_vault`, que
tem a logica. Desligado (`passagem_enabled` ausente ou falso em `config.json`), nao abre o banco
nem le a transcricao. Nunca levanta: o hook de uma sessao nao pode quebrar a sessao.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

CONFIG_PATH = Path.home() / ".delegation_core" / "config.json"


def _config() -> dict:
    try:
        d = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _payload(raw: str) -> dict:
    try:
        d = json.loads(raw) if raw and raw.strip() else {}
        return d if isinstance(d, dict) else {}
    except ValueError:
        return {}


def ao_comecar(raw: str) -> None:
    """Imprime a passagem aceita (o stdout de um hook de inicio vai para o contexto do agente)."""
    from .. import passagem_vault

    cfg = _config()
    if not passagem_vault.ligado(cfg):
        return
    texto = passagem_vault.ao_comecar(cfg, _payload(raw))
    if texto:
        print(texto)


def ao_terminar(raw: str) -> None:
    from .. import passagem_vault
    from . import session_export

    cfg = _config()
    if not passagem_vault.ligado(cfg):
        return
    payload = _payload(raw)
    caminho = payload.get("transcript_path") or ""
    mensagens: list[dict] = []
    if caminho and Path(caminho).exists():
        for m in session_export._parse_transcript(caminho):
            texto, _ = session_export._redigir(m.get("text", ""))
            mensagens.append({**m, "text": texto})
    passagem_vault.ao_terminar(cfg, payload, mensagens)
    sys.stderr.write("passagem: sessao encerrada\n")
