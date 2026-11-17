import unittest
import asyncio
from delegation_core.cores.orchestration.pipeline import OrchestrationPipeline

class TestOrchestrationCore(unittest.TestCase):
    def setUp(self):
        self.pipeline = OrchestrationPipeline()

    def test_pipeline_execution(self):
        async def step_a():
            return "step_a_ok"

        async def step_b():
            return "step_b_ok"

        steps = [
            {"name": "node_a", "action": step_a, "deps": []},
            {"name": "node_b", "action": step_b, "deps": ["node_a"]}
        ]
        res = asyncio.run(self.pipeline.execute_task_workflow("test_flow", steps))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["dag_nodes_executed"], 2)
        self.assertIn("node_a", res["step_results"])
        self.assertIn("node_b", res["step_results"])
        self.assertGreater(res["telemetry"]["total_tokens"], 0)

    def test_ci_runner(self):
        res = self.pipeline.ci.inspect_pr_and_verify(42, "feat/test")
        self.assertEqual(res["status"], "VERIFIED_OK")
        self.assertEqual(res["tests_passed"], 48)

if __name__ == "__main__":
    unittest.main()
