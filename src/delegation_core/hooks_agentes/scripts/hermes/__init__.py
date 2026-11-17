"""Plugin Hermes do delegation-core (porte do plugin Python do RTK).

Registra um `pre_tool_call` que reescreve o comando do terminal quando um
filtro o conhece. Falha aberto: qualquer erro deixa o comando como veio.
"""

import os
import shutil
import subprocess
import sys

# No Windows, o processo do Hermes pode nao ter console: pede um console oculto ao filho (0 fora do Windows).
SEM_JANELA = 0x08000000 if os.name == "nt" else 0


def register(ctx):
    ctx.register_hook("pre_tool_call", _pre_tool_call)


def _reescrever(command):
    try:
        from delegation_core.hooks_agentes.nucleo import decidir
        return decidir(command)
    except ImportError:
        if shutil.which("delegation-core") is None:
            return None
        r = subprocess.run(["delegation-core", "rewrite", command], capture_output=True, text=True, timeout=2,
                           creationflags=SEM_JANELA)
        return r.stdout.strip() if r.returncode == 3 else None


def _pre_tool_call(tool_name=None, args=None, **_kwargs):
    try:
        if tool_name != "terminal" or not isinstance(args, dict):
            return
        command = args.get("command")
        if not isinstance(command, str) or not command.strip():
            return
        novo = _reescrever(command)
        if novo and novo != command:
            args["command"] = novo
    except Exception as e:  # noqa: BLE001
        print(f"delegation-core: hermes plugin warning: {e}", file=sys.stderr)
