"""Processos filhos que nao abrem janela de console no Windows.

No Windows, um programa de console (`python.exe`, `git.exe`, `nvidia-smi.exe`,
`schtasks.exe`, `tesseract.exe`) lancado por um processo SEM console ganha um console
novo e VISIVEL, mesmo com a saida capturada. O daemon, o dashboard (um app grafico) e os
hooks rodam sem console, entao cada filho deles piscava uma janela preta, e um filho de
longa duracao a deixava aberta. `CREATE_NO_WINDOW` pede ao Windows um console oculto, que
os netos herdam: um unico filho marcado cobre a arvore abaixo dele.

Uso, em toda chamada de `subprocess` que captura a saida:

    subprocess.run(cmd, capture_output=True, text=True, **sem_janela())

Nao serve para chamada que precisa escrever no terminal do usuario: sem console, a saida
do filho nao tem para onde ir. Essas sao poucas (so ramos de Linux e macOS) e a guarda
`tests/test_sem_janela_de_console.py` exige que cada chamada seja uma coisa ou outra.
"""

from __future__ import annotations

import os

# `subprocess.CREATE_NO_WINDOW` so existe no Windows; o valor e o da API do Win32.
CREATE_NO_WINDOW = 0x08000000


def _e_windows() -> bool:
    return os.name == "nt"


def sem_janela(**kwargs) -> dict:
    """kwargs de `subprocess` que impedem o Windows de abrir um console novo.

    Fora do Windows devolve os `kwargs` sem mudar nada, entao a mesma linha serve nas
    tres plataformas. Preserva `creationflags` que o chamador ja tenha passado.
    """
    if _e_windows():
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | CREATE_NO_WINDOW
    return kwargs


# ── guarda global (24/11/2026) ───────────────────────────────────────────────
#
# `sem_janela()` depende de cada chamada lembrar dele, e nao alcanca o que as bibliotecas
# (torch, huggingface, psutil...) lancam por conta propria. A guarda corrige os flags de TODO
# `subprocess.Popen` do processo, que e por onde passam `run`, `call`, `check_output`,
# `os.popen` e o `asyncio` do Windows (`windows_utils.Popen` herda dele). `os.system` nao passa
# pelo Popen e e trocado tambem. Ela e ligada no `import delegation_core`, entao cobre o
# daemon, a CLI, os hooks e qualquer filho Python nosso.

DETACHED_PROCESS = 0x00000008
CREATE_NEW_CONSOLE = 0x00000010


def ajustar_flags(flags: int, tem_console: bool) -> int:
    """Os `creationflags` que nunca abrem um console visivel.

    - `CREATE_NEW_CONSOLE` e pedido explicito de janela (diagnostico): fica como esta.
    - `DETACHED_PROCESS` vira `CREATE_NO_WINDOW`: o filho sem console nenhum abriria uma
      janela VISIVEL para cada neto de console que lancasse; com o console oculto, os netos o
      herdam e nenhum abre janela.
    - Sem console no processo atual (pythonw, ou ele proprio desanexado), todo filho de console
      ganharia um console novo e visivel: recebe `CREATE_NO_WINDOW`.
    - Com console (o terminal do usuario, ou o console oculto que o Claude Code da aos hooks), o
      filho herda esse console e nao abre janela; acrescentar o flag lhe daria outro console e
      a saida de um comando do `shell` deixaria de chegar ao terminal. Fica como esta.
    """
    flags = int(flags or 0)
    if flags & CREATE_NEW_CONSOLE:
        return flags
    if flags & DETACHED_PROCESS:
        return (flags & ~DETACHED_PROCESS) | CREATE_NO_WINDOW
    if not tem_console:
        return flags | CREATE_NO_WINDOW
    return flags


def tem_console() -> bool:
    """Se o processo atual esta ligado a algum console, visivel ou oculto (so Windows)."""
    try:
        import ctypes
        return ctypes.windll.kernel32.GetConsoleCP() != 0
    except Exception:   # noqa: BLE001  sem a API, supoe o pior e esconde
        return False


def instalar_guarda(classe=None, modulo_os=None, forcar: bool = False) -> bool:
    """Liga a guarda uma vez por processo. Fora do Windows nao faz nada (salvo `forcar`, para os
    testes). Devolve se ela esta ligada. `classe` e `modulo_os` existem para os testes."""
    if not (_e_windows() or forcar):
        return False
    import subprocess
    classe = classe or subprocess.Popen
    modulo_os = modulo_os or os
    if getattr(classe.__init__, "_dc_sem_janela", False):
        return True
    original = classe.__init__

    def __init__(self, *args, **kwargs):
        kwargs["creationflags"] = ajustar_flags(kwargs.get("creationflags", 0), tem_console())
        original(self, *args, **kwargs)

    __init__._dc_sem_janela = True
    __init__.__wrapped__ = original
    classe.__init__ = __init__

    def system(comando):
        # `os.system` chama o cmd.exe pelo C, fora do Popen: no pythonw abria janela.
        return subprocess.call(comando, shell=True)

    system._dc_sem_janela = True
    modulo_os.system = system
    return True
