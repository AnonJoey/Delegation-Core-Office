"""
agent_guard.py — Guardião unificado de execução de agentes locais.
Fusão de Paperclip (Travas atômicas e concorrência com TTL) + Hermes (Orçamento de iterações) + OpenClaw (Gateway).
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Dict, Any

DEFAULT_LOCK_DIR = Path(os.environ.get("DELEGATION_CORE_HOME", Path.home() / ".delegation_core")) / "locks"


class AgentExecutionGuard:
    """Controle de concorrência atômico, travas em disco com TTL e controle de iterações."""

    def __init__(self, max_concurrent: int = 4, default_budget_iterations: int = 25, lock_ttl_sec: float = 300.0):
        self.max_concurrent = max_concurrent
        self.default_budget = default_budget_iterations
        self.lock_ttl_sec = lock_ttl_sec
        self.active_locks: Dict[str, float] = {}
        self.sessions: Dict[str, int] = {}
        self.lock_dir = DEFAULT_LOCK_DIR
        try:
            self.lock_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def _clean_stale_locks(self):
        now = time.time()
        # Limpeza em memória
        stale = [aid for aid, ts in self.active_locks.items() if now - ts > self.lock_ttl_sec]
        for aid in stale:
            del self.active_locks[aid]

        # Limpeza em disco
        if self.lock_dir.exists():
            for f in self.lock_dir.glob("*.lock"):
                try:
                    if now - f.stat().st_mtime > self.lock_ttl_sec:
                        f.unlink(missing_ok=True)
                except Exception:
                    pass

    def acquire_lock(self, agent_id: str) -> bool:
        self._clean_stale_locks()
        if len(self.active_locks) >= self.max_concurrent:
            return False

        # Criação de trava atômica em disco (padrão Paperclip)
        lock_file = self.lock_dir / f"{agent_id}.lock"
        try:
            fd = os.open(str(lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w") as fp:
                fp.write(f"pid={os.getpid()}\ntime={time.time()}\n")
        except FileExistsError:
            # Trava já existe em disco
            return False
        except Exception:
            pass  # Fallback apenas para memória se disco falhar

        self.active_locks[agent_id] = time.time()
        return True

    def release_lock(self, agent_id: str):
        if agent_id in self.active_locks:
            del self.active_locks[agent_id]

        lock_file = self.lock_dir / f"{agent_id}.lock"
        try:
            lock_file.unlink(missing_ok=True)
        except Exception:
            pass

    def check_iteration_budget(self, session_id: str) -> Dict[str, Any]:
        curr = self.sessions.get(session_id, 0) + 1
        self.sessions[session_id] = curr

        allowed = curr <= self.default_budget
        return {
            "session_id": session_id,
            "iteration": curr,
            "max_budget": self.default_budget,
            "within_budget": allowed,
            "status": "PERMITTED" if allowed else "BUDGET_EXCEEDED_HALT",
        }
