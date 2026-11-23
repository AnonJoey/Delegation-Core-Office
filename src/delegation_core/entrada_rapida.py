"""Ponto de entrada do comando `delegation-core` (item 6.1.2).

Tres subcomandos rodam a cada comando Bash do agente: `shell`, `filters hook` e, quando o
agente pede, `recall`. Montar o argparse de todos os subcomandos do `cli` custava ~50 ms por
chamada (medido em 23/11/2026). Aqui eles sao reconhecidos pela forma exata e vao ao daemon
pelo `cliente_fino`; qualquer outra coisa, ou qualquer falha do daemon, segue para `cli.main`
de sempre, sem mudar nada.

A forma tem que ser exata de proposito: `shell --help`, `recall` sem hash ou com opcao
desconhecida caem no argparse, que sabe explicar o erro.
"""

from __future__ import annotations

import sys


def _recall_argv(argv: list[str]) -> tuple[str, int] | None:
    """`recall <hash>`, `recall <hash> --from N` ou `recall <hash> --from=N`; senao None."""
    if len(argv) == 2 and not argv[1].startswith("-"):
        return argv[1], 0
    if len(argv) == 4 and not argv[1].startswith("-") and argv[2] == "--from" and argv[3].isdigit():
        return argv[1], int(argv[3])
    if len(argv) == 3 and not argv[1].startswith("-") and argv[2].startswith("--from=") and argv[2][7:].isdigit():
        return argv[1], int(argv[2][7:])
    return None


def _shell(comando: str) -> int:
    from . import cliente_fino
    codigo = cliente_fino.shell(comando)
    if codigo is not None:
        return codigo
    # O daemon nao atendeu antes de o comando rodar: o caminho local roda, sem o argparse.
    from types import SimpleNamespace
    from .filtros_saida.cli import cmd_run
    return cmd_run(SimpleNamespace(comando=comando))


def _hook() -> int:
    import json
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0  # hook nunca derruba a chamada
    if not isinstance(payload, dict):
        return 0
    from . import cliente_fino
    atendido, resposta = cliente_fino.hook(payload)
    if not atendido:
        from .filtros_saida.cli import reescrever
        resposta = reescrever(payload)
    if resposta:
        print(json.dumps(resposta))
    return 0


def _recall(h: str, a_partir: int) -> int:
    from . import cliente_fino
    r = cliente_fino.recall(h, a_partir)
    if r is None:
        from types import SimpleNamespace
        from .filtros_saida.cli import cmd_recall
        return cmd_recall(SimpleNamespace(hash=h, from_line=a_partir))
    if not r.get("found"):
        print(f"{h}: not found", file=sys.stderr)
        return 1
    print(r.get("output", ""))
    return 0


def main() -> int:
    if sys.stdout is None or sys.stderr is None:
        # O mesmo cuidado do `cli.main` com processo sem console (pythonw.exe), so quando falta.
        from .stdio_nulo import garantir_stdio
        garantir_stdio()
    argv = sys.argv[1:]
    if len(argv) == 2 and argv[0] == "shell" and not argv[1].startswith("-"):
        return _shell(argv[1])
    if argv == ["filters", "hook"]:
        return _hook()
    if argv and argv[0] == "recall":
        alvo = _recall_argv(argv)
        if alvo is not None:
            return _recall(*alvo)
    from .cli import main as principal
    return principal()


if __name__ == "__main__":
    sys.exit(main())
