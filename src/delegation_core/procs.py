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
