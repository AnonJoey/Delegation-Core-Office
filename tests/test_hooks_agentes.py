"""Hooks em Python, um por host: reescrevem so comando conhecido e simples, nunca concedem permissao."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from delegation_core.hooks_agentes import HOSTS, decidir, responder
from delegation_core.hooks_agentes.cli import cmd_rewrite

SCRIPTS = Path(__file__).resolve().parents[1] / "src" / "delegation_core" / "hooks_agentes" / "scripts"


def test_decisao():
    assert decidir("terraform plan") == "delegation-core shell 'terraform plan'"
    assert decidir("pytest -x") == "delegation-core shell 'pytest -x'", "modulo Rust anotado tambem"
    for c in ("ls | head", "git status && ls", "echo $(date)", "comando-desconhecido", "delegation-core shell x", ""):
        assert decidir(c) is None, c


def _resp(host, payload):
    s = responder(host, json.dumps(payload))
    return None if s is None else json.loads(s)


def test_formato_de_cada_host():
    c = {"command": "terraform plan", "description": "d"}
    r = _resp("claude", {"tool_name": "Bash", "tool_input": c})["hookSpecificOutput"]
    assert r["updatedInput"]["command"].startswith("delegation-core shell") and r["updatedInput"]["description"] == "d"
    assert _resp("codex", {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": c})
    assert _resp("vscode", {"tool_name": "run_in_terminal", "tool_input": c})
    cli = _resp("copilot-cli", {"toolName": "bash", "toolArgs": json.dumps(c)})
    assert cli["modifiedArgs"]["command"].startswith("delegation-core") and "permissionDecision" not in cli
    ide = _resp("copilot-ide", {"toolName": "run_in_terminal", "toolArgs": json.dumps(c)})
    assert ide["permissionDecision"] == "deny" and "re-run" in ide["permissionDecisionReason"]
    g = _resp("gemini", {"tool_name": "run_shell_command", "tool_input": c})
    assert g["decision"] == "ask_user" and g["hookSpecificOutput"]["tool_input"]["command"].startswith("delegation-core")
    a = _resp("antigravity", {"toolCall": {"name": "run_command", "args": {"CommandLine": "terraform plan"}}})
    assert a["overwrite"]["CommandLine"].startswith("delegation-core")
    assert _resp("vibe", {"tool_name": "bash", "tool_input": c})["hook_specific_output"]
    assert _resp("trae", {"tool_name": "RunCommand", "tool_input": c})["hookSpecificOutput"]["updatedInput"]
    assert _resp("droid", {"tool_name": "Execute", "tool_input": c})
    cur = _resp("cursor", {"tool_input": c})
    assert cur["permission"] == "ask" and cur["updated_input"]["command"].startswith("delegation-core")


def test_nunca_concede_permissao():
    c = {"command": "terraform plan"}
    payloads = {"claude": {"tool_name": "Bash", "tool_input": c},
                "codex": {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": c},
                "vscode": {"tool_name": "Bash", "tool_input": c}, "trae": {"tool_name": "RunCommand", "tool_input": c},
                "droid": {"tool_name": "Bash", "tool_input": c},
                "copilot-cli": {"toolName": "bash", "toolArgs": json.dumps(c)}}
    for host, p in payloads.items():
        texto = responder(host, json.dumps(p))
        assert '"allow"' not in texto, host


def test_entrada_ruim_falha_aberto():
    for host in HOSTS:
        for entrada in ("", "nao e json", "[1,2]", json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls | wc"}})):
            s = responder(host, entrada)
            assert s is None or json.loads(s) in ({}, {"decision": "allow"}), (host, entrada)


def test_rewrite_codigos_de_saida(capsys):
    assert cmd_rewrite(SimpleNamespace(comando="helm list")) == 3
    assert capsys.readouterr().out.strip() == "delegation-core shell 'helm list'"
    assert cmd_rewrite(SimpleNamespace(comando="comando-desconhecido")) == 1


def test_script_python_de_verdade():
    """O script do Claude, executado como o Claude Code executaria."""
    p = subprocess.run([sys.executable, str(SCRIPTS / "claude.py")], capture_output=True, text=True,
                       input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "helm list"}}), timeout=30)
    assert json.loads(p.stdout)["hookSpecificOutput"]["updatedInput"]["command"] == "delegation-core shell 'helm list'"
    assert sorted(f.stem for f in SCRIPTS.glob("*.py")) == sorted(h.replace("-", "_") for h in HOSTS)


def test_plugin_hermes():
    import importlib.util
    spec = importlib.util.spec_from_file_location("plugin_hermes", SCRIPTS / "hermes" / "__init__.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    registrados = {}
    m.register(SimpleNamespace(register_hook=lambda nome, f: registrados.setdefault(nome, f)))
    args = {"command": "helm list"}
    registrados["pre_tool_call"](tool_name="terminal", args=args)
    assert args["command"] == "delegation-core shell 'helm list'"
