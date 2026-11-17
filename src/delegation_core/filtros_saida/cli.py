"""`delegation-core shell`, `delegation-core recall`, `delegation-core filters`.

- `shell "<comando>"` roda o comando com `/bin/sh -c` e mostra a saida
  filtrada (se algum filtro casa) com a mesma decisao do RTK. O codigo de saida
  e o do comando. Sem filtro, a saida passa intacta. stderr vai direto para o
  terminal, salvo filtro com `filter_stderr`.
- `recall <hash> [--from N]` devolve a saida original guardada.
- `filters list | verify | hook`:
  `hook` le o payload PreToolUse do Claude Code na entrada padrao e, quando o
  comando Bash e simples e um filtro casa, devolve `updatedInput` com o comando
  embrulhado em `delegation-core shell`. NUNCA devolve
  `permissionDecision`: a permissao continua sendo do Claude Code e do usuario
  (o RTK so concede quando uma regra do proprio usuario ja concederia; aqui nem
  isso). Comando composto (pipe, `&&`, `;`, redirecionamento, subshell) passa
  sem mudanca.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys

_COMPOSTO = re.compile(r"[|;&<>`\n]|\$\(")


def cmd_run(args) -> int:
    from . import execucao, motor
    comando = args.comando
    from . import modulos
    # Modulo que roda o comando por conta propria (git, gh): consulta a ferramenta mais de
    # uma vez e monta o resultado, como o `run_*` do RTK.
    rodavel = modulos.rodavel(comando)
    if rodavel is not None:
        from .modulos.ambiente import Ambiente
        amb = Ambiente()
        codigo = modulos.rodar_modulo(rodavel, amb)
        amb.flush()
        return codigo
    achado = modulos.modulo_para(comando)
    if achado is not None:
        # Modulo do RTK portado: stdout e stderr juntos, como no RTK, salvo o
        # modulo que o RTK roda com `stdout_only` (o stderr segue para o stderr).
        so_stdout = getattr(achado[1], "SO_STDOUT", False)
        p = subprocess.run(["/bin/sh", "-c", modulos.comando_do_rtk(comando)], stdout=subprocess.PIPE,
                           stderr=None if so_stdout else subprocess.STDOUT)
        print(modulos.aplicar(comando, p.stdout.decode("utf-8", "replace"), p.returncode, injetado=True)["output"])
        return p.returncode
    f = motor.achar(comando)
    juntar = bool(f and f.filter_stderr)
    p = subprocess.run(["/bin/sh", "-c", comando], stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE if juntar else None)
    saida = p.stdout.decode("utf-8", "replace")
    if juntar:
        saida += (p.stderr or b"").decode("utf-8", "replace")
    if f is None:
        # Comando de um modulo Rust do RTK (anotado, nao portado): compressor do delegation-core.
        from . import modulos_rtk
        m = modulos_rtk.modulo_para(comando)
        if m is None:
            sys.stdout.write(saida)
            return p.returncode
        from ..compressao.roteador import comprimir
        tipo = m["delegation_core_route"] if m["delegation_core_route"] in ("diff", "search", "log", "text") else "auto"
        # Sem Kompress: ele carrega um modelo de ~1,5 GB por processo e leva de 3 a 7 s
        # para ganhar de 19 a 25% de tamanho. O `shell` roda a cada comando Bash do agente
        # (pelo hook), e cada comando e um processo novo. O Kompress continua no daemon.
        print(comprimir(saida, comando, tipo, kompress=False)["output"])
        return p.returncode
    r = execucao.exibir(f, saida, comando, p.returncode)
    print(r["output"])
    return p.returncode


def cmd_recall(args) -> int:
    from . import execucao
    r = execucao.recuperar(args.hash, args.from_line)
    if r is None:
        print(f"{args.hash}: not found", file=sys.stderr)
        return 1
    print(r["output"])
    return 0


def reescrever(payload: dict, executavel: str = "delegation-core") -> dict | None:
    """A resposta do hook, ou None para deixar o comando como esta."""
    from . import motor
    if payload.get("tool_name") not in (None, "Bash"):
        return None
    entrada = payload.get("tool_input") or {}
    comando = (entrada.get("command") or "").strip()
    if not comando or _COMPOSTO.search(comando) or comando.startswith(executavel):
        return None
    if motor.achar(comando) is None:
        return None
    novo = dict(entrada, command=f"{executavel} shell {shlex.quote(comando)}")
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecisionReason": "delegation-core output filter",
                                   "updatedInput": novo}}


def cmd_filters(args) -> int:
    from . import motor
    if args.acao == "list":
        for f in motor.carregar():
            print(f"{f.nome:22} {f.origem:8} {f.descricao}")
        return 0
    if args.acao == "verify":
        r = motor.verificar()
        print(f"{r['passed']}/{r['total']} inline tests passed across {r['filters']} filters")
        for falha in r["failed"]:
            print(f"FAIL {falha['filter']} / {falha['test']}\n  expected: {falha['expected']!r}\n  actual:   {falha['actual']!r}")
        return 0 if not r["failed"] else 1
    if args.acao == "hook":
        try:
            payload = json.loads(sys.stdin.read() or "{}")
        except ValueError:
            return 0  # hook nunca derruba a chamada
        r = reescrever(payload)
        if r:
            print(json.dumps(r))
        return 0
    return 1


def registrar(sub) -> dict:
    p = sub.add_parser("shell", help="Run a shell command and show its output through the RTK filters")
    p.add_argument("comando", help="the command line, run with /bin/sh -c")
    p = sub.add_parser("recall", help="Original output saved when a filter cut it")
    p.add_argument("hash")
    p.add_argument("--from", dest="from_line", type=int, default=0)
    p = sub.add_parser("filters", help="Output filters: list, verify (RTK inline tests), hook (Claude Code PreToolUse)")
    p.add_argument("acao", choices=["list", "verify", "hook"])
    return {"shell": cmd_run, "recall": cmd_recall, "filters": cmd_filters}
