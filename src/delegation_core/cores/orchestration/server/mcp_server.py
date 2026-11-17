import json
import sys
import asyncio
from typing import Dict, Any
from ..pipeline import OrchestrationPipeline

class OrchestrationMCPServer:
    def __init__(self):
        self.pipeline = OrchestrationPipeline()

    def handle_rpc(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if method == "workflow.run_demo":
            title = params.get("title", "CI-CD Autonomous Pipeline")
            
            async def step_fetch():
                await asyncio.sleep(0.01)
                return {"files_checked": 12}

            async def step_test():
                await asyncio.sleep(0.02)
                return {"tests_passed": 48}

            steps = [
                {"name": "checkout", "action": step_fetch, "deps": []},
                {"name": "run_suite", "action": step_test, "deps": ["checkout"]}
            ]
            return asyncio.run(self.pipeline.execute_task_workflow(title, steps))
            
        elif method == "ci.verify_pr":
            pr_id = params.get("pr_id", 101)
            branch = params.get("branch", "main")
            return self.pipeline.ci.inspect_pr_and_verify(pr_id, branch)

        elif method == "telemetry.status":
            return self.pipeline.telemetry.get_summary()

        elif method == "system.status":
            return {
                "server": "orchestration-core",
                "version": "1.0.0",
                "components": [
                    "DAGEngine (Dagu)",
                    "AgentTaskQueue (Multica/Fleetbase)",
                    "AutonomousCIRunner (Pullfrog)",
                    "LLMTelemetryTracker (LangWatch)"
                ]
            }
        else:
            return {"error": f"Method '{method}' not found"}

    def run_stdio_loop(self):
        sys.stderr.write("[OrchestrationCore] Servidor MCP ativo via stdio...\n")
        for line in sys.stdin:
            if not line.strip():
                continue
            try:
                req = json.loads(line)
                res = {"jsonrpc": "2.0", "id": req.get("id"), "result": self.handle_rpc(req.get("method"), req.get("params", {}))}
                sys.stdout.write(json.dumps(res) + "\n")
                sys.stdout.flush()
            except Exception as e:
                err = {"jsonrpc": "2.0", "id": None, "error": str(e)}
                sys.stdout.write(json.dumps(err) + "\n")
                sys.stdout.flush()
