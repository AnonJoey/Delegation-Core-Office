import inspect
import uuid
import time
from typing import Dict, Any, List
from .dag.engine import DAGEngine
from .dispatch.task_queue import AgentTaskQueue
from .dispatch.ci_runner import AutonomousCIRunner
from .telemetry.tracker import LLMTelemetryTracker

class OrchestrationPipeline:
    """Motor unificado consolidando Dagu + Multica + Pullfrog + Fleetbase + LangWatch"""
    def __init__(self):
        self.queue = AgentTaskQueue()
        self.ci = AutonomousCIRunner()
        self.telemetry = LLMTelemetryTracker()

    async def execute_task_workflow(self, task_title: str, workflow_steps: List[Dict[str, Any]]) -> Dict[str, Any]:
        trace_id = str(uuid.uuid4())[:8]
        t_start = time.time()
        
        # 1. Enfileiramento da tarefa (Multica / Fleetbase)
        task_id = self.queue.enqueue(task_title, {"trace_id": trace_id}, priority=2)
        self.queue.claim_next()  # reclama a proxima da fila; o retorno nunca foi usado
        
        # 2. Construcao e execucao do DAG (Dagu)
        dag = DAGEngine(f"dag_{trace_id}")
        
        for step in workflow_steps:
            s_name = step["name"]
            s_action = step["action"]
            s_deps = step.get("deps", [])
            
            # Wrapper com telemetria automatica (LangWatch)
            async def wrapped_action(act=s_action, name=s_name, in_tok=step.get("in_tokens", 120), out_tok=step.get("out_tokens", 60)):
                t0 = time.time()
                if inspect.iscoroutinefunction(act):
                    res = await act()
                else:
                    res = act()
                dur = time.time() - t0
                self.telemetry.record_span(trace_id, name, "local-gemma-12b", in_tok, out_tok, dur)
                return res

            dag.add_node(s_name, wrapped_action, s_deps)

        dag_results = await dag.run()
        total_duration = round(time.time() - t_start, 4)

        return {
            "pipeline": "orchestration-core",
            "task_id": task_id,
            "trace_id": trace_id,
            "status": "SUCCESS",
            "total_duration_sec": total_duration,
            "dag_nodes_executed": len(dag_results),
            "telemetry": self.telemetry.get_summary(),
            "step_results": dag_results
        }
