"""
telemetria.py — Camada de Observabilidade e Rastreamento de Spans (Inspirado no LangWatch).
Coleta métricas de execução de ferramentas MCP, tempos de inferência e contagem de tokens,
com persistência local em SQLite e agregação de telemetria para o Dashboard.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

DB_PATH = Path(os.environ.get("DELEGATION_CORE_HOME", Path.home() / ".delegation_core")) / "telemetria.db"
_local = threading.local()
_lock = threading.Lock()


def _get_connection(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=60.0)
    conn.execute("PRAGMA busy_timeout = 60000;")
    return conn


def _init_telemetry_db(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = _get_connection(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("""
    CREATE TABLE IF NOT EXISTS spans (
        span_id TEXT PRIMARY KEY,
        trace_id TEXT NOT NULL,
        name TEXT NOT NULL,
        span_type TEXT NOT NULL,
        caller TEXT,
        started_at REAL NOT NULL,
        duration_ms REAL,
        tokens_in INTEGER DEFAULT 0,
        tokens_out INTEGER DEFAULT 0,
        status TEXT NOT NULL,
        error_msg TEXT,
        metadata_json TEXT
    );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_spans_trace ON spans(trace_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_spans_started ON spans(started_at);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_spans_type ON spans(span_type);")
    conn.commit()
    conn.close()


class Telemetria:
    """Gerenciador central de observabilidade e métricas de execução."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        _init_telemetry_db(self.db_path)

    @contextmanager
    def span(self, name: str, span_type: str = "mcp_tool", caller: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):
        span_id = f"sp_{uuid.uuid4().hex[:8]}"
        trace_id = getattr(_local, "trace_id", None) or f"tr_{uuid.uuid4().hex[:8]}"
        _local.trace_id = trace_id

        started_at = time.time()
        record = {
            "tokens_in": 0,
            "tokens_out": 0,
            "metadata": dict(metadata or {})
        }
        status = "ok"
        error_msg = None

        try:
            yield record
        except Exception as e:
            status = "error"
            error_msg = str(e)
            raise
        finally:
            duration_ms = (time.time() - started_at) * 1000
            self._save_span(
                span_id=span_id,
                trace_id=trace_id,
                name=name,
                span_type=span_type,
                caller=caller,
                started_at=started_at,
                duration_ms=duration_ms,
                tokens_in=record["tokens_in"],
                tokens_out=record["tokens_out"],
                status=status,
                error_msg=error_msg,
                metadata_json=json.dumps(record["metadata"], ensure_ascii=False)
            )

    def _save_span(self, span_id: str, trace_id: str, name: str, span_type: str,
                   caller: Optional[str], started_at: float, duration_ms: float,
                   tokens_in: int, tokens_out: int, status: str, error_msg: Optional[str], metadata_json: str):
        with _lock:
            try:
                conn = _get_connection(self.db_path)
                with conn:
                    conn.execute("""
                        INSERT INTO spans (span_id, trace_id, name, span_type, caller, started_at, duration_ms, tokens_in, tokens_out, status, error_msg, metadata_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (span_id, trace_id, name, span_type, caller, started_at, duration_ms, tokens_in, tokens_out, status, error_msg, metadata_json))
                conn.close()
            except Exception as e:
                logger.warning("Falha ao salvar span de telemetria '%s': %s", name, e)

    def get_summary(self, hours: float = 24.0) -> Dict[str, Any]:
        """Calcula o resumo de métricas para a janela de tempo especificada."""
        since = time.time() - (hours * 3600)
        conn = _get_connection(self.db_path)
        conn.row_factory = sqlite3.Row

        totals = conn.execute("""
            SELECT count(*) as total_calls,
                   sum(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as total_errors,
                   avg(duration_ms) as avg_duration_ms,
                   sum(tokens_in) as total_tokens_in,
                   sum(tokens_out) as total_tokens_out
            FROM spans
            WHERE started_at >= ?
        """, (since,)).fetchone()

        by_type = conn.execute("""
            SELECT span_type, count(*) as count, avg(duration_ms) as avg_ms
            FROM spans
            WHERE started_at >= ?
            GROUP BY span_type
        """, (since,)).fetchall()

        by_name = conn.execute("""
            SELECT name, count(*) as count, avg(duration_ms) as avg_ms,
                   sum(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as errors
            FROM spans
            WHERE started_at >= ?
            GROUP BY name
            ORDER BY count DESC
            LIMIT 10
        """, (since,)).fetchall()

        conn.close()

        total_calls = totals["total_calls"] or 0
        total_errors = totals["total_errors"] or 0
        error_rate = (total_errors / total_calls * 100) if total_calls else 0.0

        return {
            "period_hours": hours,
            "total_calls": total_calls,
            "total_errors": total_errors,
            "error_rate_pct": round(error_rate, 2),
            "avg_duration_ms": round(totals["avg_duration_ms"] or 0.0, 2),
            "tokens_in": totals["total_tokens_in"] or 0,
            "tokens_out": totals["total_tokens_out"] or 0,
            "by_type": [dict(r) for r in by_type],
            "top_tools": [dict(r) for r in by_name]
        }

    def get_recent_spans(self, limit: int = 50) -> List[Dict[str, Any]]:
        conn = _get_connection(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT span_id, trace_id, name, span_type, caller, started_at, duration_ms, tokens_in, tokens_out, status, error_msg
            FROM spans
            ORDER BY started_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]


_telemetry_singleton = Telemetria()

def get_telemetria() -> Telemetria:
    return _telemetry_singleton
