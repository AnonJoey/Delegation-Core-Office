"""
test_novas_ferramentas_mcp.py — Teste de integração das novas ferramentas MCP no server.
"""

import json
from pathlib import Path
from delegation_core.server import convert_to_markdown, dag_run, dag_status


def test_convert_to_markdown_tool(tmp_path: Path):
    f = tmp_path / "teste.csv"
    f.write_text("A,B\n1,2\n", encoding="utf-8")
    resp_raw = convert_to_markdown(str(f))
    resp = json.loads(resp_raw)
    assert resp["status"] == "ok"
    assert "| A | B |" in resp["markdown"]


def test_dag_run_and_status_tools():
    yaml_wf = """
    name: mcp_teste_dag
    steps:
      - id: s1
        command: "echo 'dag mcp ok'"
    """
    run_resp = json.loads(dag_run(yaml_wf))
    assert run_resp["status"] == "ok"
    run_id = run_resp["run_id"]

    stat_resp = json.loads(dag_status(run_id))
    assert stat_resp["status"] == "ok"
    assert stat_resp["data"]["run"]["status"] == "success"


