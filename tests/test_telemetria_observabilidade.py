"""
test_telemetria_observabilidade.py — Testes unitários do módulo de telemetria e observabilidade.
"""

import time
import pytest
from pathlib import Path
from delegation_core.telemetria import Telemetria


def test_telemetria_record_spans(tmp_path: Path):
    db_file = tmp_path / "telemetry_test.db"
    tel = Telemetria(db_path=db_file)

    with tel.span(name="search_vault", span_type="mcp_tool", caller="claude_code") as rec:
        rec["tokens_in"] = 50
        rec["tokens_out"] = 200
        time.sleep(0.01)

    summary = tel.get_summary(hours=1.0)
    assert summary["total_calls"] == 1
    assert summary["total_errors"] == 0
    assert summary["tokens_in"] == 50
    assert summary["tokens_out"] == 200
    assert summary["avg_duration_ms"] > 0.0

    recent = tel.get_recent_spans(limit=10)
    assert len(recent) == 1
    assert recent[0]["name"] == "search_vault"
    assert recent[0]["status"] == "ok"


def test_telemetria_record_error(tmp_path: Path):
    db_file = tmp_path / "telemetry_test.db"
    tel = Telemetria(db_path=db_file)

    with pytest.raises(ValueError):
        with tel.span(name="tool_com_falha", span_type="mcp_tool"):
            raise ValueError("Erro simulado")

    summary = tel.get_summary(hours=1.0)
    assert summary["total_calls"] == 1
    assert summary["total_errors"] == 1
    assert summary["error_rate_pct"] == 100.0
