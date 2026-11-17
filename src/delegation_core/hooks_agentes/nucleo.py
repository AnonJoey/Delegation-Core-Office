"""Decisao de reescrita e o formato de resposta de cada host (de hook_cmd.rs do RTK)."""

from __future__ import annotations

import json
import re
import shlex

EXECUTAVEL = "delegation-core"
_COMPOSTO = re.compile(r"[|;&<>`\n]|\$\(")


def decidir(comando: str) -> str | None:
    """O comando reescrito, ou None para deixar como esta.

    Reescreve quando um filtro TOML do RTK casa ou quando o comando e de um
    modulo Rust anotado (a saida passa pelo compressor do delegation-core).
    """
    from ..filtros_saida import modulos_rtk, motor
    c = (comando or "").strip()
    if not c or _COMPOSTO.search(c) or c.startswith(EXECUTAVEL):
        return None
    if motor.achar(c) is None and modulos_rtk.modulo_para(c) is None:
        return None
    return f"{EXECUTAVEL} shell {shlex.quote(c)}"


def _pre_tool_use(payload: dict, novo: str) -> dict:
    entrada = dict(payload.get("tool_input") or {})
    entrada["command"] = novo
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecisionReason": "delegation-core output filter",
                                   "updatedInput": entrada}}


def _comando(payload: dict, *caminho: str) -> str:
    v = payload
    for k in caminho:
        v = v.get(k) if isinstance(v, dict) else None
    return v if isinstance(v, str) else ""


def _claude(p):
    if p.get("tool_name") not in (None, "Bash"):
        return None
    novo = decidir(_comando(p, "tool_input", "command"))
    return _pre_tool_use(p, novo) if novo else None


def _codex(p):
    if p.get("hook_event_name") not in (None, "PreToolUse") or p.get("tool_name") not in ("Bash", "bash"):
        return None
    novo = decidir(_comando(p, "tool_input", "command"))
    return _pre_tool_use(p, novo) if novo else None


def _vscode(p):
    if p.get("tool_name") not in ("runTerminalCommand", "run_in_terminal", "Bash", "bash"):
        return None
    novo = decidir(_comando(p, "tool_input", "command"))
    return _pre_tool_use(p, novo) if novo else None


def _args_copilot(p):
    if p.get("toolName") not in ("bash", "powershell", "run_in_terminal"):
        return None
    try:
        args = json.loads(p.get("toolArgs") or "")
    except ValueError:
        return None
    return args if isinstance(args, dict) else None


def _copilot_cli(p):
    args = _args_copilot(p)
    if args is None or p.get("toolName") == "run_in_terminal":
        return None
    novo = decidir(args.get("command") or "")
    if not novo:
        return None
    return {"permissionDecisionReason": "delegation-core output filter", "modifiedArgs": dict(args, command=novo)}


def _copilot_ide(p):
    """A IDE nao aceita reescrita: nega com a sugestao do comando (como o RTK)."""
    args = _args_copilot(p)
    if args is None or p.get("toolName") != "run_in_terminal":
        return None
    novo = decidir(args.get("command") or "")
    if not novo:
        return None
    return {"permissionDecision": "deny",
            "permissionDecisionReason": f"delegation-core output filter: re-run this command as `{novo}` instead."}


def _gemini(p):
    if p.get("tool_name") != "run_shell_command":
        return {"decision": "allow"}
    novo = decidir(_comando(p, "tool_input", "command"))
    if not novo:
        return {"decision": "allow"}
    return {"decision": "ask_user", "hookSpecificOutput": {"tool_input": {"command": novo}}}


def _antigravity(p):
    chamada = p.get("toolCall") or {}
    if chamada.get("name") != "run_command":
        return {"decision": "allow"}
    a = chamada.get("args") or {}
    novo = decidir(a.get("CommandLine") or a.get("command") or a.get("cmd") or "")
    if not novo:
        return {"decision": "allow"}
    return {"decision": "allow", "reason": "Rewritten by delegation-core output filter.",
            "overwrite": {"CommandLine": novo}}


def _vibe(p):
    if p.get("tool_name") != "bash":
        return None
    novo = decidir(_comando(p, "tool_input", "command"))
    if not novo:
        return None
    return {"hook_specific_output": {"tool_input": {"command": novo}},
            "system_message": f"delegation-core: rewrote to `{novo}`"}


def _trae(p):
    if p.get("tool_name") != "RunCommand":
        return None
    novo = decidir(_comando(p, "tool_input", "command"))
    if not novo:
        return None
    entrada = dict(p.get("tool_input") or {}, command=novo)
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "updatedInput": entrada}}


def _droid(p):
    if p.get("tool_name", "") not in ("Execute", "Bash", ""):
        return None
    novo = decidir(_comando(p, "tool_input", "command"))
    return _pre_tool_use(p, novo) if novo else None


def _cursor(p):
    novo = decidir(_comando(p, "tool_input", "command"))
    if not novo:
        return {}
    return {"continue": True, "permission": "ask", "updated_input": {"command": novo}}


HOSTS = {"claude": _claude, "codex": _codex, "vscode": _vscode, "copilot-cli": _copilot_cli,
         "copilot-ide": _copilot_ide, "gemini": _gemini, "antigravity": _antigravity, "vibe": _vibe,
         "trae": _trae, "droid": _droid, "cursor": _cursor}


def responder(host: str, entrada: str) -> str | None:
    """Texto a imprimir na saida padrao, ou None para nao imprimir nada. Nunca levanta."""
    texto = (entrada or "").lstrip("﻿").strip()
    vazio = {"cursor": "{}", "gemini": '{"decision":"allow"}', "antigravity": '{"decision":"allow"}'}.get(host)
    if not texto:
        return vazio
    try:
        payload = json.loads(texto)
    except ValueError:
        return vazio
    if not isinstance(payload, dict):
        return vazio
    try:
        r = HOSTS[host](payload)
    except Exception:  # noqa: BLE001 - hook falha aberto: o comando segue como veio
        return vazio
    return None if r is None else json.dumps(r, ensure_ascii=False)
