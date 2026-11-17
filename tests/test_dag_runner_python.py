"""
test_dag_runner_python.py — Testes unitários do orquestrador de DAG em Python.
"""

import pytest
from pathlib import Path
from delegation_core.dag_runner import DAGRunner, DAGExecutionError


def test_dag_runner_execution_success(tmp_path: Path):
    db_file = tmp_path / "dag_test.db"
    runner = DAGRunner(db_path=db_file)

    yaml_spec = """
    name: pipeline_teste
    steps:
      - id: etapa_1
        command: "echo 'etapa 1 executada'"
      - id: etapa_2
        command: "echo 'etapa 2 executada'"
        depends_on: [etapa_1]
    """

    wf = runner.parse_yaml(yaml_spec)
    run_id = runner.execute_workflow(wf)

    status = runner.get_run_status(run_id)
    assert status is not None
    assert status["run"]["status"] == "success"
    assert status["run"]["completed_steps"] == 2
    assert len(status["steps"]) == 2


def test_dag_runner_cycle_detection(tmp_path: Path):
    db_file = tmp_path / "dag_test.db"
    runner = DAGRunner(db_path=db_file)

    yaml_cycle = """
    name: pipeline_com_ciclo
    steps:
      - id: passo_a
        command: "echo 'A'"
        depends_on: [passo_b]
      - id: passo_b
        command: "echo 'B'"
        depends_on: [passo_a]
    """

    wf = runner.parse_yaml(yaml_cycle)
    with pytest.raises(DAGExecutionError) as exc_info:
        runner.execute_workflow(wf)
    assert "Ciclo detectado" in str(exc_info.value)


def test_dag_runner_step_failure(tmp_path: Path):
    db_file = tmp_path / "dag_test.db"
    runner = DAGRunner(db_path=db_file)

    yaml_failure = """
    name: pipeline_falha
    steps:
      - id: passo_que_falha
        command: "exit 1"
      - id: passo_dependente
        command: "echo 'nao deve rodar'"
        depends_on: [passo_que_falha]
    """

    wf = runner.parse_yaml(yaml_failure)
    run_id = runner.execute_workflow(wf)

    status = runner.get_run_status(run_id)
    assert status["run"]["status"] == "failed"
    step_map = {s["step_id"]: s for s in status["steps"]}
    assert step_map["passo_que_falha"]["status"] == "failed"
    assert step_map["passo_dependente"]["status"] == "skipped"
