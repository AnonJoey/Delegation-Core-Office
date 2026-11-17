"""
unified_facade.py: Ponto de entrada unificado para os 5 núcleos consolidados
do ecossistema no delegation-core-TEST:
- Agent Harness Core (Categoria 1: Skills FTS5 + Anti-slop + Ferramentas)
- Multimodal Media Core (Categoria A: OCRmyPDF + MarkItDown + Whisper + Audiblez + DeepDiagram)
- Orchestration Core (Categoria 3: Dagu DAG + Multica/Fleetbase Fila + Pullfrog CI + LangWatch Telemetria)
- Local Platform Core (Categoria 4: Headroom/RTK Pruner + Paperclip/Hermes Guard + Graphify/Memgraph + GS-Server Telemetria)
"""

import time
from typing import Dict, Any, List, Optional

from .agent_harness.server import AgentHarnessServer

from .multimodal.pipeline import MultimodalPipeline
from .orchestration.pipeline import OrchestrationPipeline
from .platform.platform_engine import UnifiedLocalPlatform
from .self_hosted.gateway import HomelabServiceGateway


class UnifiedCoresBridge:
    """
    Fachada unificada para invocação programática e integração MCP
    dos 6 núcleos de software consolidados.
    """

    def __init__(self, skills_db_path: Optional[str] = None):
        self.agent_harness = AgentHarnessServer(skills_db_path)
        self.multimodal = MultimodalPipeline()
        self.orchestration = OrchestrationPipeline()
        self.platform = UnifiedLocalPlatform()
        self.self_hosted = HomelabServiceGateway()

    # --- Agent Harness & Skills ---
    def search_skills(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        return self.agent_harness.skills.search(query, limit)

    def get_skill_by_id(self, skill_id: int) -> Optional[Dict[str, Any]]:
        return self.agent_harness.skills.get_by_id(skill_id)

    def sanitize_text(self, text: str) -> Dict[str, Any]:
        audit = self.agent_harness.sanitizer.audit(text)
        purified = self.agent_harness.sanitizer.purify(text)
        return {
            "audit": audit,
            "purified": purified,
            "is_clean": audit["is_clean"],
            "score": audit["score"],
        }

    # --- Multimodal & Assets ---
    def ingest_multimodal_asset(self, file_path: str) -> Dict[str, Any]:
        return self.multimodal.ingest_asset(file_path)

    def synthesize_speech(self, text: str, output_path: str = "output.mp3") -> Dict[str, Any]:
        return self.multimodal.synthesize_speech(text, output_path)

    def generate_diagram(self, prompt: str) -> Dict[str, Any]:
        return self.multimodal.generate_diagram(prompt)

    # --- Orchestration & DAG ---
    async def execute_task_workflow(
        self, task_title: str, workflow_steps: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        return await self.orchestration.execute_task_workflow(task_title, workflow_steps)

    def verify_ci_pr(self, pr_id: int, branch: str = "main") -> Dict[str, Any]:
        return self.orchestration.ci.inspect_pr_and_verify(pr_id, branch)

    def get_llm_telemetry(self) -> Dict[str, Any]:
        return self.orchestration.telemetry.get_summary()

    # --- Local Platform ---
    def execute_agent_session(
        self, session_id: str, prompt: str, target_module: str = "core"
    ) -> Dict[str, Any]:
        return self.platform.execute_agent_session(session_id, prompt, target_module)

    def prune_context(self, raw_text: str) -> Dict[str, Any]:
        return self.platform.pruner.prune_context(raw_text)

    def query_code_graph(self, cypher: str) -> Dict[str, Any]:
        return self.platform.graph.query_cypher_mock(cypher)

    def get_hardware_metrics(self) -> Dict[str, Any]:
        return self.platform.hardware.get_server_metrics()

    # --- Self-Hosted & Homelab Gateway ---
    def list_homelab_services(self, domain: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.self_hosted.list_services(domain)

    def route_homelab_service(
        self,
        target_service: str,
        action: str,
        user_token: str = "local-admin",
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self.self_hosted.route_request(
            target_service=target_service,
            action=action,
            user_token=user_token,
            payload=payload,
        )

    def get_homelab_health(self) -> Dict[str, Any]:
        return self.self_hosted.check_health()

    # --- Status Consolidado ---
    def get_unified_status(self) -> Dict[str, Any]:
        harness_stats = self.agent_harness.skills.get_stats()
        hw_metrics = self.platform.hardware.get_server_metrics()
        telemetry = self.orchestration.telemetry.get_summary()
        homelab_health = self.self_hosted.check_health()

        total_skills = sum(v["count"] for v in harness_stats.values()) if harness_stats else 0

        return {
            "status": "OPERATIONAL",
            "timestamp": time.time(),
            "cores_active": [
                "agent-harness-core",
                "multimodal-media-core",
                "orchestration-core",
                "local-platform-core",
                "homelab-gateway-core",
            ],
            "skills": {
                "total_indexed": total_skills,
                "sources": list(harness_stats.keys()),
            },
            "multimodal_capabilities": [
                "OCRmyPDF", "MarkItDown", "Whisper", "Audiblez", "DeepDiagram"
            ],
            "orchestrator": {
                "dag_engine": "Dagu-Async",
                "ci_agent": "Pullfrog",
                "queue": "Multica/Fleetbase",
                "telemetry": telemetry,
            },
            "local_platform": {
                "hardware": hw_metrics,
                "context_reducer": "Headroom AST + RTK 8-Stage",
                "agent_guard": "Paperclip Locks + Hermes Budget",
                "code_graph": "Graphify + Memgraph MVCC",
            },
            "self_hosted_gateway": homelab_health,
        }


# Instância singleton padrão para conveniência
_GLOBAL_BRIDGE: Optional[UnifiedCoresBridge] = None

def get_cores_bridge() -> UnifiedCoresBridge:
    global _GLOBAL_BRIDGE
    if _GLOBAL_BRIDGE is None:
        _GLOBAL_BRIDGE = UnifiedCoresBridge()
    return _GLOBAL_BRIDGE
