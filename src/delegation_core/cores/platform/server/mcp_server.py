import json
import sys
from typing import Dict, Any
from ..platform_engine import UnifiedLocalPlatform

class LocalPlatformMCPServer:
    def __init__(self):
        self.platform = UnifiedLocalPlatform()

    def handle_rpc(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if method == "agent.session":
            sid = params.get("session_id", "sess_01")
            prompt = params.get("prompt", "Executar analise de seguranca")
            return self.platform.execute_agent_session(sid, prompt)
            
        elif method == "hardware.metrics":
            return self.platform.hardware.get_server_metrics()

        elif method == "prune.tokens":
            text = params.get("text", "")
            return self.platform.pruner.prune_context(text)

        elif method == "graph.query":
            q = params.get("cypher", "MATCH (n) RETURN n LIMIT 10")
            return self.platform.graph.query_cypher_mock(q)

        elif method == "system.status":
            return {
                "server": "local-platform-core",
                "version": "1.0.0",
                "integrated_frameworks": [
                    "Delegation-Core", "Headroom", "RTK", "Paperclip",
                    "Hermes-Agent", "OpenClaw", "Graphify", "Memgraph",
                    "GS-Server", "Grafana", "Voicebox", "OBLITERATUS", "GobboNet"
                ]
            }
        else:
            return {"error": f"Method '{method}' not found"}

    def run_stdio_loop(self):
        sys.stderr.write("[LocalPlatformCore] Servidor MCP ativo via stdio...\n")
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
