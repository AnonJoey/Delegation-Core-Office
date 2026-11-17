"""
engine.py — Motor de execução de DAG declarativo assíncrono (inspirado no Dagu).
Fusão com delegation_core.dag_runner (resolução topológica, retries e persistência SQLite WAL).
"""

from __future__ import annotations

import asyncio
import inspect
import time
import uuid
from typing import Dict, List, Any, Optional

from .node import TaskNode
from delegation_core.dag_runner import _get_db, _init_db, DB_PATH


class DAGEngine:
    """Motor de execução de DAG assíncrono com suporte a persistência SQLite."""

    def __init__(self, name: str, db_path=None):
        self.name = name
        self.nodes: Dict[str, TaskNode] = {}
        self.db_path = db_path or DB_PATH
        try:
            _init_db(self.db_path)
        except Exception:
            pass

    def add_node(
        self,
        name: str,
        action,
        dependencies: Optional[List[str]] = None,
        max_retries: int = 1,
    ):
        self.nodes[name] = TaskNode(name, action, dependencies, max_retries)

    async def run(self) -> Dict[str, Any]:
        results = {}
        pending = set(self.nodes.keys())
        running = {}
        run_id = f"async_dag_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        started_at = time.time()

        # Registro inicial no SQLite WAL
        try:
            conn = _get_db(self.db_path)
            conn.execute(
                """
                INSERT INTO dag_runs (run_id, dag_name, status, total_steps, completed_steps, started_at)
                VALUES (?, ?, 'running', ?, 0, ?)
                """,
                (run_id, self.name, len(self.nodes), started_at),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

        try:
            while pending or running:
                # Seleciona nós cujas dependências foram concluídas
                ready = [
                    n
                    for n in pending
                    if all(dep in results for dep in self.nodes[n].dependencies)
                ]
                for node_name in ready:
                    pending.remove(node_name)
                    node = self.nodes[node_name]
                    node.status = "RUNNING"
                    running[node_name] = asyncio.create_task(self._execute_node(node))

                if not running:
                    if pending:
                        raise RuntimeError(
                            f"Ciclo detectado ou dependências não resolvidas: {pending}"
                        )
                    break

                done, _ = await asyncio.wait(
                    running.values(), return_when=asyncio.FIRST_COMPLETED
                )
                for task in done:
                    for n_name, t in list(running.items()):
                        if t == task:
                            del running[n_name]
                            node = self.nodes[n_name]
                            res = task.result()
                            node.result = res
                            results[n_name] = res

                            # Persistir step
                            try:
                                conn = _get_db(self.db_path)
                                conn.execute(
                                    """
                                    INSERT INTO dag_step_runs (run_id, step_id, status, duration_ms, exit_code, stdout, stderr)
                                    VALUES (?, ?, 'success', ?, 0, ?, '')
                                    """,
                                    (
                                        run_id,
                                        n_name,
                                        node.duration_sec * 1000.0,
                                        str(res)[:500],
                                    ),
                                )
                                conn.commit()
                                conn.close()
                            except Exception:
                                pass
                            break

            # Finalizar run
            try:
                conn = _get_db(self.db_path)
                conn.execute(
                    """
                    UPDATE dag_runs
                    SET status = 'completed', completed_steps = ?, finished_at = ?
                    WHERE run_id = ?
                    """,
                    (len(results), time.time(), run_id),
                )
                conn.commit()
                conn.close()
            except Exception:
                pass

        except Exception as e:
            try:
                conn = _get_db(self.db_path)
                conn.execute(
                    """
                    UPDATE dag_runs
                    SET status = 'failed', finished_at = ?, error = ?
                    WHERE run_id = ?
                    """,
                    (time.time(), str(e), run_id),
                )
                conn.commit()
                conn.close()
            except Exception:
                pass
            raise e

        return results

    async def _execute_node(self, node: TaskNode):
        t0 = time.time()
        for attempt in range(node.max_retries + 1):
            try:
                if inspect.iscoroutinefunction(node.action):
                    res = await node.action()
                else:
                    res = node.action()
                node.status = "COMPLETED"
                node.duration_sec = round(time.time() - t0, 4)
                return res
            except Exception as e:
                if attempt == node.max_retries:
                    node.status = "FAILED"
                    node.error = str(e)
                    node.duration_sec = round(time.time() - t0, 4)
                    raise e
                await asyncio.sleep(0.05)
