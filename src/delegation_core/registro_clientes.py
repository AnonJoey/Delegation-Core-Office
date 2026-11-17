"""Estado do registro do delegation-core em cada cliente MCP: o `doctor` le, nada escreve.

Trazido do `rea doctor`, que classifica cada registro de cliente como
alinhado, velho, ausente ou invalido. O delegation-core ja sabia escrever os
registros (`clients.py`, `clientes_extra.py`) e consertar os quebrados
(`installer.repair_client_configs`), mas nada dizia, sem escrever, em que
estado cada um esta. Token trocado, porta mudada ou o Desktop reescrevendo o
proprio arquivo eram descobertos quando o cliente parava de achar as
ferramentas.

Estados:
- `aligned`: a entrada e exatamente a que `clients ...` escreveria hoje;
- `stale`: existe, mas difere (URL, token, forma);
- `missing`: o cliente esta instalado (o arquivo existe) e nao tem a entrada;
- `invalid`: o arquivo existe e nao se le;
- `not_installed`: nem o arquivo do cliente existe. Nao e problema.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path


def _json(caminho: Path, raiz: str, esperado: dict) -> tuple[str, str]:
    if not caminho.exists():
        return "not_installed", ""
    try:
        bruto = caminho.read_text(encoding="utf-8").strip()
        dados = json.loads(bruto) if bruto else {}
    except (OSError, ValueError) as e:
        return "invalid", f"{type(e).__name__}"
    if not isinstance(dados, dict) or not isinstance(dados.get(raiz, {}), dict):
        return "invalid", f"{raiz} is not an object"
    from .clients import SELF
    atual = (dados.get(raiz) or {}).get(SELF)
    if atual is None:
        return "missing", ""
    if atual == esperado:
        return "aligned", ""
    difere = sorted(k for k in set(atual) | set(esperado) if atual.get(k) != esperado.get(k)) if isinstance(atual, dict) else ["entry"]
    return "stale", "differs in: " + ", ".join(difere)


def _codex(cfg) -> tuple[str, str]:
    from . import clients
    if not clients.CODEX_CONFIG.exists():
        return "not_installed", ""
    try:
        dados = tomllib.loads(clients.CODEX_CONFIG.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        return "invalid", type(e).__name__
    atual = (dados.get("mcp_servers") or {}).get(clients.SELF)
    if atual is None:
        return "missing", ""
    esperado = tomllib.loads(clients.codex_block(cfg))["mcp_servers"][clients.SELF]
    difere = sorted(k for k in esperado if atual.get(k) != esperado[k])
    return ("aligned", "") if not difere else ("stale", "differs in: " + ", ".join(difere))


def estado(cfg) -> list[dict]:
    from . import clientes_extra, clients
    alvos = [
        ("claude-code", lambda: _json(Path.home() / ".claude.json", "mcpServers", clients.claude_code_entry(cfg)),
         Path.home() / ".claude.json", "--claude-code"),
        ("claude-desktop", lambda: _json(clients.claude_desktop_config_path(), "mcpServers", clients.claude_desktop_entry(cfg)),
         clients.claude_desktop_config_path(), "--claude-desktop"),
        ("codex", lambda: _codex(cfg), clients.CODEX_CONFIG, "--codex"),
        ("antigravity", lambda: _json(clients.ANTIGRAVITY_CONFIG, "mcpServers", clients.antigravity_entry(cfg)),
         clients.ANTIGRAVITY_CONFIG, "--antigravity"),
        ("cursor", lambda: _json(clientes_extra.cursor_config(), "mcpServers", clientes_extra.cursor_entry(cfg)),
         clientes_extra.cursor_config(), "--cursor"),
        ("opencode", lambda: _json(clientes_extra.opencode_config(), "mcp", clientes_extra.opencode_entry(cfg)),
         clientes_extra.opencode_config(), "--opencode"),
    ]
    saida = []
    for nome, checar, caminho, flag in alvos:
        try:
            st, detalhe = checar()
        except Exception as e:  # noqa: BLE001 - um cliente quebrado nao derruba o resto
            st, detalhe = "invalid", f"{type(e).__name__}: {e}"
        item = {"client": nome, "status": st, "path": str(caminho)}
        if detalhe:
            item["detail"] = detalhe
        if st in ("stale", "missing"):
            item["fix"] = f"delegation-core clients {flag}"
        saida.append(item)
    return saida


def check(cfg) -> dict:
    itens = estado(cfg)
    ruins = [i for i in itens if i["status"] in ("stale", "invalid")]
    faltam = [i for i in itens if i["status"] == "missing"]
    resumo = ", ".join(f"{i['client']}={i['status']}" for i in itens if i["status"] != "not_installed")
    if ruins:
        return {"check": "client_registrations", "status": "warn",
                "detail": resumo, "fix": "; ".join(i.get("fix", f"look at {i['path']}") for i in ruins),
                "clients": itens}
    return {"check": "client_registrations", "status": "ok",
            "detail": resumo or "no MCP client config found" + (f" ({len(faltam)} without delegation-core)" if faltam else ""),
            "clients": itens}
