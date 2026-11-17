#!/usr/bin/env python3
"""Hook do delegation-core para o host 'trae' (porte em Python do hook do RTK).

Le o payload do host na entrada padrao e responde no formato dele. Reescreve
so comando simples que um filtro conhece, e nunca concede permissao. Se o
pacote delegation-core nao estiver importavel neste Python, chama o comando
`delegation-core hook trae`; se nem isso existir, nao imprime nada (o comando
segue como veio).
"""
import os
import subprocess
import sys

# No Windows, o hook pode nascer sem console: pede um console oculto ao filho (0 fora do Windows).
SEM_JANELA = 0x08000000 if os.name == "nt" else 0

HOST = "trae"

try:
    from delegation_core.hooks_agentes.nucleo import responder
except ImportError:
    entrada = sys.stdin.read()
    try:
        r = subprocess.run(["delegation-core", "hook", HOST], input=entrada, capture_output=True, text=True, timeout=5,
                           creationflags=SEM_JANELA)
        sys.stdout.write(r.stdout)
    except (OSError, subprocess.SubprocessError):
        pass
    raise SystemExit(0)

saida = responder(HOST, sys.stdin.read())
if saida is not None:
    print(saida)
