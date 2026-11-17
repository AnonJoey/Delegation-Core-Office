"""
tracker.py — Rastreador de telemetria LLM integrado ao motor central de telemetria do delegation-core.
Fusão com delegation_core.telemetria (persistência SQLite WAL e LangWatch tracing).
"""

from __future__ import annotations

import time
from typing import Dict, Any, List

from delegation_core.telemetria import get_telemetria


class LLMTelemetryTracker:
    """Observabilidade, tracing e controle de orçamento de tokens (LangWatch)."""

    def __init__(self):
        self.spans: List[Dict[str, Any]] = []
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self._telemetria_db = get_telemetria()

    def record_span(
        self,
        trace_id: str,
        span_name: str,
        model: str,
        in_tokens: int,
        out_tokens: int,
        duration_sec: float,
    ) -> Dict[str, Any]:
        duration_ms = round(duration_sec * 1000.0, 2)
        span = {
            "trace_id": trace_id,
            "span_name": span_name,
            "model": model,
            "in_tokens": in_tokens,
            "out_tokens": out_tokens,
            "total_tokens": in_tokens + out_tokens,
            "duration_sec": round(duration_sec, 4),
            "timestamp": time.time(),
        }
        self.spans.append(span)
        self.total_input_tokens += in_tokens
        self.total_output_tokens += out_tokens

        # Persistência unificada no SQLite WAL de telemetria
        try:
            self._telemetria_db.record_span(
                trace_id=trace_id,
                name=span_name,
                span_type="llm_inference",
                caller=model,
                duration_ms=duration_ms,
                tokens_in=in_tokens,
                tokens_out=out_tokens,
                status="ok",
                metadata={"engine": "orchestration_core"},
            )
        except Exception:
            pass  # Falha no banco não aborta a execução do pipeline

        return span

    def get_summary(self) -> Dict[str, Any]:
        total_tok = self.total_input_tokens + self.total_output_tokens
        db_summary = {}
        try:
            db_summary = self._telemetria_db.get_summary(hours=24.0)
        except Exception:
            pass

        return {
            "total_spans": len(self.spans),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": total_tok,
            "avg_span_latency_sec": (
                round(sum(s["duration_sec"] for s in self.spans) / len(self.spans), 4)
                if self.spans
                else 0.0
            ),
            "persistent_db": db_summary,
        }
