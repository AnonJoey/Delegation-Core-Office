import time
from typing import Dict, Any
from .pruner.token_reducer import TokenPruningEngine
from .guard.agent_guard import AgentExecutionGuard
from .graph.code_graph import CodeGraphEngine
from .telemetry.hardware import HardwareSupervisor
from .voice.voice_server import VoiceboxEngine
from .cleaner.code_sweeper import CodeSweeperAndNet

class UnifiedLocalPlatform:
    """
    Plataforma Unificada do Ecossistema Local consolidando 15 ferramentas:
    Delegation-Core + Headroom + RTK + Paperclip + Hermes + OpenClaw +
    Graphify + Memgraph + GS-Server + Grafana + Voicebox + OBLITERATUS + GobboNet + N8N
    """
    def __init__(self):
        self.pruner = TokenPruningEngine()
        self.guard = AgentExecutionGuard(max_concurrent=4, default_budget_iterations=30)
        self.graph = CodeGraphEngine()
        self.hardware = HardwareSupervisor()
        self.voice = VoiceboxEngine()
        self.cleaner = CodeSweeperAndNet()

    def execute_agent_session(self, session_id: str, prompt: str, target_module: str = "core") -> Dict[str, Any]:
        t0 = time.time()
        
        # 1. Auditoria de Hardware do Servidor (gs-server / grafana)
        hw_info = self.hardware.get_server_metrics()
        
        # 2. Travas de Concorrencia e Orcamento de Iteracoes (paperclip / hermes-agent)
        agent_id = f"agent_{session_id}"
        locked = self.guard.acquire_lock(agent_id)
        if not locked:
            return {
                "pipeline": "local-platform-core",
                "session_id": session_id,
                "execution_status": "BLOCKED",
                "reason": "Max concurrency reached or lock could not be acquired",
                "agent_guard": {"concurrency_lock": False, "budget": None},
            }

        try:
            budget = self.guard.check_iteration_budget(session_id)
            if not budget["within_budget"]:
                return {
                    "pipeline": "local-platform-core",
                    "session_id": session_id,
                    "execution_status": "HALTED",
                    "reason": "Iteration budget exceeded",
                    "agent_guard": {"concurrency_lock": True, "budget": budget},
                }

            # 3. Poda de Contexto e Reducao de Tokens (headroom / rtk)
            pruned_res = self.pruner.prune_context(prompt)
            
            # 4. Consulta ao Grafo de Codigo (graphify / memgraph)
            graph_res = self.graph.build_module_graph(target_module, ["ASTNode", "Visitor", "Executor"])
            
            # 5. Feedback de Audio (voicebox)
            voice_res = self.voice.stream_speech_feedback("Comando processado no ecossistema local")
        finally:
            self.guard.release_lock(agent_id)
        
        duration = round(time.time() - t0, 4)

        return {
            "pipeline": "local-platform-core",
            "session_id": session_id,
            "execution_status": "SUCCESS",
            "duration_sec": duration,
            "hardware_telemetry": hw_info,
            "agent_guard": {"concurrency_lock": locked, "budget": budget},
            "token_pruning": {
                "tokens_saved": pruned_res["tokens_saved_estimate"],
                "reduction_ratio": pruned_res["reduction_ratio"]
            },
            "code_graph": graph_res,
            "voice_feedback": voice_res
        }
