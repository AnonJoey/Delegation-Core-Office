"""`delegation-core rewrite "<cmd>"` e `delegation-core hook <host>`."""

from __future__ import annotations

import sys


def cmd_rewrite(args) -> int:
    """Codigos como os do `rtk rewrite`: 3 = reescrito (pedir confirmacao), 1 = sem reescrita.

    Nunca devolve 0 (reescrito e liberado): conceder permissao nao e papel do hook.
    """
    from .nucleo import decidir
    novo = decidir(args.comando)
    if novo is None:
        return 1
    print(novo)
    return 3


def cmd_hook(args) -> int:
    from .nucleo import responder
    saida = responder(args.host, sys.stdin.read())
    if saida is not None:
        print(saida)
    return 0


def registrar(sub) -> dict:
    from .nucleo import HOSTS
    p = sub.add_parser("rewrite", help="Rewrite a shell command to run through the output filters (exit 3) or not (exit 1)")
    p.add_argument("comando", help="the shell command to rewrite")
    p = sub.add_parser("hook", help="Agent hook: read the host's PreToolUse payload on stdin, answer in its format")
    p.add_argument("host", choices=sorted(HOSTS), help="agent whose hook payload format is used")
    return {"rewrite": cmd_rewrite, "hook": cmd_hook}
