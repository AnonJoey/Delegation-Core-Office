"""As notas do vault, sem nada mais: busca, sonho, vigia e historico precisam so disto.

Morava em historico_vault.py, e quem so queria a lista importava o historico
inteiro, que importa o notewriter: era o ciclo busca_hibrida -> historico_vault
-> notewriter -> ... -> busca_hibrida.
"""

from __future__ import annotations

import os
from pathlib import Path


def notas_do_vault(cfg) -> list[str]:
    """Caminhos relativos de toda nota .md nas pastas do vault, sem diretorio oculto."""
    raiz = Path(cfg.vault)
    saida = []
    for pasta in getattr(cfg, "vault_folders", []) or []:
        base = raiz / pasta
        if not base.is_dir():
            continue
        for dirpath, dirnames, arquivos in os.walk(base):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for a in arquivos:
                if a.endswith(".md"):
                    saida.append(str((Path(dirpath) / a).relative_to(raiz)))
    return saida
