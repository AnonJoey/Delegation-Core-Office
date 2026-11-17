"""Cursor e OpenCode apontando para o daemon: os dois clientes com adaptador no
Paperclip que faltavam em `clients.py`.

Mesmo cuidado do `install_antigravity`: o arquivo pode ter servidores de outras
ferramentas, entao so a nossa entrada e reescrita; JSON invalido e recusado em
vez de sobrescrito; a primeira versao vira `.dc-backup`; a escrita e atomica.

Formatos (documentacao de cada cliente, nao testados contra o cliente rodando):
- Cursor, `~/.cursor/mcp.json`: `mcpServers.<nome> = {url, headers}`.
- OpenCode, `~/.config/opencode/opencode.json`: `mcp.<nome> = {type: "remote",
  url, headers, enabled}`.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .clients import SELF


def cursor_config() -> Path:
    return Path.home() / ".cursor" / "mcp.json"


def opencode_config() -> Path:
    return Path.home() / ".config" / "opencode" / "opencode.json"


def cursor_entry(cfg) -> dict:
    return {"url": cfg.server_url, "headers": {"Authorization": f"Bearer {cfg.server_token}"}}


def opencode_entry(cfg) -> dict:
    return {"type": "remote", "url": cfg.server_url, "enabled": True,
            "headers": {"Authorization": f"Bearer {cfg.server_token}"}}


def _instalar(cliente: str, caminho: Path, raiz: str, entrada: dict) -> dict:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    dados: dict = {}
    if caminho.exists():
        bruto = caminho.read_text(encoding="utf-8").strip()
        if bruto:
            try:
                lido = json.loads(bruto)
            except json.JSONDecodeError:
                return {"client": cliente, "path": str(caminho), "status": "error",
                        "detail": f"{caminho.name} is not valid JSON: not touching it"}
            if not isinstance(lido, dict):
                return {"client": cliente, "path": str(caminho), "status": "error",
                        "detail": f"{caminho.name} is not a JSON object: not touching it"}
            dados = lido
    servidores = dados.setdefault(raiz, {})
    if not isinstance(servidores, dict):
        return {"client": cliente, "path": str(caminho), "status": "error",
                "detail": f"{raiz} is not an object: not touching it"}
    antes = servidores.get(SELF)
    servidores[SELF] = entrada
    if antes == entrada:
        return {"client": cliente, "path": str(caminho), "status": "already-configured"}
    if caminho.exists() and caminho.stat().st_size:
        copia = caminho.with_suffix(caminho.suffix + ".dc-backup")
        if not copia.exists():
            shutil.copy2(caminho, copia)
    tmp = caminho.with_suffix(caminho.suffix + ".tmp")
    tmp.write_text(json.dumps(dados, indent=2) + "\n", encoding="utf-8")
    tmp.replace(caminho)
    return {"client": cliente, "path": str(caminho), "status": "updated" if antes else "installed"}


def install_cursor(cfg) -> dict:
    return _instalar("cursor", cursor_config(), "mcpServers", cursor_entry(cfg))


def install_opencode(cfg) -> dict:
    return _instalar("opencode", opencode_config(), "mcp", opencode_entry(cfg))
