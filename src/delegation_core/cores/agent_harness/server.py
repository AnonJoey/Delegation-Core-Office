import json
import sys
from typing import Dict, Any
from .skills.registry import SkillsRegistry
from .sanitizer.engine import PromptSanitizer
from .tools.reverse_eng import ReverseEngTool

class AgentHarnessServer:
    def __init__(self, db_path: str = None):
        self.skills = SkillsRegistry(db_path)
        self.sanitizer = PromptSanitizer()
        self.rea = ReverseEngTool()

    def handle_rpc(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if method == "skills.search":
            q = params.get("query", "")
            limit = params.get("limit", 5)
            return {"results": self.skills.search(q, limit)}
            
        elif method == "skills.get":
            skill_id = params.get("id")
            return {"skill": self.skills.get_by_id(skill_id)}
            
        elif method == "sanitizer.audit":
            text = params.get("text", "")
            return self.sanitizer.audit(text)
            
        elif method == "sanitizer.purify":
            text = params.get("text", "")
            return {"cleaned": self.sanitizer.purify(text)}
            
            
        elif method == "tools.inspect_code":
            path = params.get("file_path", "")
            return self.rea.inspect_python_file(path)
            
        elif method == "system.status":
            return {
                "server": "agent-harness-core",
                "version": "1.0.0",
                "skills_indexed": self.skills.get_stats(),
                "mcp_tools": ["skills.search", "skills.get", "sanitizer.audit", "sanitizer.purify", "tools.inspect_code"]
            }
            
        else:
            return {"error": f"Method '{method}' not found"}

    def run_stdio_loop(self):
        """Executa protocolo MCP / JSON-RPC sobre stdio"""
        sys.stderr.write("[AgentHarnessCore] Servidor MCP ativo via stdio...\n")
        for line in sys.stdin:
            if not line.strip():
                continue
            try:
                req = json.loads(line)
                method = req.get("method", "")
                params = req.get("params", {})
                req_id = req.get("id")
                
                result = self.handle_rpc(method, params)
                res = {"jsonrpc": "2.0", "id": req_id, "result": result}
                sys.stdout.write(json.dumps(res) + "\n")
                sys.stdout.flush()
            except Exception as e:
                err_res = {"jsonrpc": "2.0", "id": None, "error": str(e)}
                sys.stdout.write(json.dumps(err_res) + "\n")
                sys.stdout.flush()
