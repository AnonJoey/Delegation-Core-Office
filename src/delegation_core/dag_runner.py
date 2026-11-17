"""
dag_runner.py — Motor Leve de Execução de DAGs em Python (Inspirado no Dagu).
Orquestra tarefas acíclicas dirigidas com resolução de dependências, controle de timeouts,
retentativas automáticas e persistência de histórico de execuções em SQLite.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any

import networkx as nx
import yaml

from .procs import sem_janela

DB_PATH = Path(os.environ.get("DELEGATION_CORE_HOME", Path.home() / ".delegation_core")) / "dag_executions.db"


@dataclass
class DAGStep:
    id: str
    command: str
    depends_on: List[str] = field(default_factory=list)
    timeout: int = 120
    retries: int = 0
    cwd: Optional[str] = None


@dataclass
class DAGWorkflow:
    name: str
    steps: List[DAGStep]
    description: str = ""


def _get_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=60.0)
    conn.execute("PRAGMA busy_timeout = 60000;")
    return conn


def _init_db(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = _get_db(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS dag_runs (
        run_id TEXT PRIMARY KEY,
        dag_name TEXT NOT NULL,
        status TEXT NOT NULL,
        total_steps INTEGER,
        completed_steps INTEGER,
        started_at REAL,
        finished_at REAL,
        error TEXT
    );
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS dag_step_runs (
        run_id TEXT,
        step_id TEXT,
        status TEXT,
        duration_ms REAL,
        exit_code INTEGER,
        output TEXT,
        error TEXT,
        PRIMARY KEY(run_id, step_id),
        FOREIGN KEY(run_id) REFERENCES dag_runs(run_id)
    );
    """)
    conn.commit()
    conn.close()


class DAGExecutionError(Exception):
    pass


class DAGRunner:
    """Executor de fluxos baseados em grafos direcionados acíclicos."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        _init_db(self.db_path)

    @classmethod
    def parse_yaml(cls, yaml_content: str) -> DAGWorkflow:
        data = yaml.safe_load(yaml_content)
        if not isinstance(data, dict):
            raise ValueError("O conteúdo YAML deve definir um dicionário no topo.")

        name = data.get("name", "unnamed_workflow")
        raw_steps = data.get("steps", [])
        if not raw_steps:
            raise ValueError("O workflow deve conter ao menos um passo em 'steps'.")

        steps = []
        for s in raw_steps:
            if not isinstance(s, dict) or "id" not in s or "command" not in s:
                raise ValueError("Cada passo deve conter 'id' e 'command'.")
            steps.append(DAGStep(
                id=s["id"],
                command=s["command"],
                depends_on=s.get("depends_on", []),
                timeout=int(s.get("timeout", 120)),
                retries=int(s.get("retries", 0)),
                cwd=s.get("cwd")
            ))

        return DAGWorkflow(name=name, steps=steps, description=data.get("description", ""))

    def execute_workflow(self, workflow: DAGWorkflow) -> str:
        """Valida e executa o DAG, persistindo estados de execução."""
        run_id = f"dag_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        g = nx.DiGraph()

        step_map: Dict[str, DAGStep] = {}
        for s in workflow.steps:
            step_map[s.id] = s
            g.add_node(s.id)
            for dep in s.depends_on:
                g.add_edge(dep, s.id)

        # Checagem de ciclos
        if not nx.is_directed_acyclic_graph(g):
            cycle = nx.find_cycle(g)
            raise DAGExecutionError(f"Ciclo detectado no DAG: {cycle}")

        # Checagem de nós fantasmas
        for node in g.nodes:
            if node not in step_map:
                raise DAGExecutionError(f"Passo dependente '{node}' não existe no workflow.")

        order = list(nx.topological_sort(g))
        started_at = time.time()

        conn = _get_db(self.db_path)
        conn.execute("""
            INSERT INTO dag_runs (run_id, dag_name, status, total_steps, completed_steps, started_at)
            VALUES (?, ?, 'running', ?, 0, ?)
        """, (run_id, workflow.name, len(order), started_at))
        conn.commit()
        conn.close()

        step_results: Dict[str, bool] = {}

        for step_id in order:
            step = step_map[step_id]
            # Verificar se alguma dependência falhou
            deps_failed = any(not step_results.get(dep, False) for dep in step.depends_on)
            if deps_failed:
                self._record_step(run_id, step_id, "skipped", 0.0, -1, "", "Dependência anterior falhou.")
                step_results[step_id] = False
                continue

            success, duration_ms, code, out, err = self._run_single_step(step)
            step_results[step_id] = success
            self._record_step(run_id, step_id, "success" if success else "failed", duration_ms, code, out, err)

        finished_at = time.time()
        final_status = "success" if all(step_results.values()) else "failed"
        completed_cnt = sum(1 for v in step_results.values() if v)

        conn = _get_db(self.db_path)
        conn.execute("""
            UPDATE dag_runs
            SET status = ?, completed_steps = ?, finished_at = ?
            WHERE run_id = ?
        """, (final_status, completed_cnt, finished_at, run_id))
        conn.commit()
        conn.close()

        return run_id

    def _run_single_step(self, step: DAGStep):
        if not step.command or "\x00" in step.command:
            return False, 0.0, 1, "", "Comando inválido ou contém caracteres nulos."

        resolved_cwd = None
        if step.cwd:
            cwd_path = Path(step.cwd).expanduser().resolve()
            if not cwd_path.is_dir():
                return False, 0.0, 1, "", f"Diretório de trabalho não existe: {step.cwd}"
            resolved_cwd = str(cwd_path)

        attempts = 0
        max_attempts = max(1, step.retries + 1)
        last_code = 1
        last_out = ""
        last_err = ""
        t0 = time.time()

        while attempts < max_attempts:
            attempts += 1
            try:
                proc = subprocess.run(
                    step.command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=step.timeout,
                    cwd=resolved_cwd,
                    **sem_janela(),
                )
                last_code = proc.returncode
                last_out = proc.stdout
                last_err = proc.stderr
                if last_code == 0:
                    duration_ms = (time.time() - t0) * 1000
                    return True, duration_ms, last_code, last_out, last_err
            except subprocess.TimeoutExpired:
                last_code = 124
                last_err = f"Passo atingiu timeout limite de {step.timeout}s."
            except Exception as e:
                last_code = 1
                last_err = str(e)

        duration_ms = (time.time() - t0) * 1000
        return False, duration_ms, last_code, last_out, last_err

    def _record_step(self, run_id: str, step_id: str, status: str, duration_ms: float, code: int, out: str, err: str):
        conn = _get_db(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO dag_step_runs (run_id, step_id, status, duration_ms, exit_code, output, error)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (run_id, step_id, status, duration_ms, code, out[:2000], err[:2000]))
        conn.commit()
        conn.close()

    def get_run_status(self, run_id: str) -> Optional[Dict[str, Any]]:
        conn = _get_db(self.db_path)
        conn.row_factory = sqlite3.Row
        run = conn.execute("SELECT * FROM dag_runs WHERE run_id = ?", (run_id,)).fetchone()
        if not run:
            conn.close()
            return None
        steps = conn.execute("SELECT * FROM dag_step_runs WHERE run_id = ? ORDER BY step_id", (run_id,)).fetchall()
        conn.close()
        return {
            "run": dict(run),
            "steps": [dict(s) for s in steps]
        }

    def list_recent_runs(self, limit: int = 10) -> List[Dict[str, Any]]:
        conn = _get_db(self.db_path)
        conn.row_factory = sqlite3.Row
        runs = conn.execute("SELECT * FROM dag_runs ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        return [dict(r) for r in runs]
