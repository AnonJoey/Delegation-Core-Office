"""Canais de atualizacao e reversao do `delegation-core update`.

Trazido do Paperclip (`update --channel stable|beta|nightly` e `--rollback`).
Aqui ha dois canais, porque e o que um checkout git sustenta sem servidor de
release:

- `branch` (padrao, o comportamento de sempre): `git pull --ff-only` no branch atual.
- `stable`: a tag de versao mais nova (`v*`, ordem de versao), em HEAD destacado.

Antes de mexer no checkout, o `update` grava o commit em que estava em
`update_history.json`. `update --rollback` volta para o ultimo registrado,
tambem em HEAD destacado: nada e apagado nem reescrito, e `git switch <branch>`
devolve o checkout ao branch.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from .arquivos_json import ler_json

CANAIS = ("branch", "stable")
MANTER = 20


def _historico() -> Path:
    from . import config
    return config.CONFIG_DIR / "update_history.json"


def ler_historico() -> list[dict]:
    return ler_json(_historico(), list)


def registrar_antes(raiz: Path, destino: str) -> dict | None:
    """Grava o commit atual antes de o update trocar o checkout."""
    from . import git_local
    codigo, sha = git_local._git(raiz, "rev-parse", "HEAD")
    if codigo != 0:
        return None
    _, ramo = git_local._git(raiz, "rev-parse", "--abbrev-ref", "HEAD")
    item = {"when": datetime.now().isoformat(timespec="seconds"), "sha": sha.strip(),
            "branch": ramo.strip(), "to": destino}
    hist = (ler_historico() + [item])[-MANTER:]
    arq = _historico()
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps(hist, indent=2), encoding="utf-8")
    tmp.replace(arq)
    return item


def tag_estavel(raiz: Path) -> str:
    """A tag de versao mais nova, depois de buscar as tags do remoto. '' se nao ha."""
    from . import git_local
    git_local._git(raiz, "fetch", "--tags", "--quiet")
    codigo, saida = git_local._git(raiz, "tag", "--list", "v[0-9]*", "--sort=-v:refname")
    if codigo != 0:
        return ""
    tags = [t.strip() for t in saida.splitlines() if t.strip()]
    return tags[0] if tags else ""


def ref_para(raiz: Path, canal: str, reverter: bool = False) -> tuple[str, str]:
    """(ref, erro). ref vazio com erro vazio quer dizer "o pull de sempre"."""
    if canal not in CANAIS:
        return "", f"unknown channel {canal!r}: use one of {', '.join(CANAIS)}"
    if reverter:
        hist = ler_historico()
        if not hist:
            return "", "no previous version recorded: nothing to roll back to"
        return hist[-1]["sha"], ""
    if canal == "stable":
        tag = tag_estavel(raiz)
        if not tag:
            return "", "no version tag (v*) found for the stable channel"
        return tag, ""
    return "", ""
