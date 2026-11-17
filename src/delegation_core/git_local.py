"""`git -C <raiz> ...` com codigo de saida e texto, sem nunca levantar excecao."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .procs import sem_janela


def _git(root: Path, *args: str, timeout: int = 60) -> tuple[int, str]:
    try:
        p = subprocess.run(["git", "-C", str(root), *args],
                           capture_output=True, text=True, timeout=timeout, **sem_janela())
        return p.returncode, (p.stdout + p.stderr).strip()
    except FileNotFoundError:
        return 127, "git not found"
    except subprocess.TimeoutExpired:
        return 124, f"git timed out after {timeout}s"
