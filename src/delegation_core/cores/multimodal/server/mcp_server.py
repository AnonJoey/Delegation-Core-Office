import json
import sys
from typing import Dict, Any
from ..pipeline import MultimodalPipeline

class MultimodalMCPServer:
    def __init__(self):
        self.pipeline = MultimodalPipeline()

    def handle_rpc(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if method == "media.ingest":
            file_path = params.get("file_path", "")
            return self.pipeline.ingest_asset(file_path)
            
        elif method == "audio.transcribe":
            file_path = params.get("audio_path", "")
            return self.pipeline.stt.transcribe(file_path)
            
        elif method == "audio.synthesize":
            text = params.get("text", "")
            out = params.get("output_path", "output.mp3")
            return self.pipeline.synthesize_speech(text, out)
            
        elif method == "diagram.generate":
            prompt = params.get("prompt", "")
            return self.pipeline.generate_diagram(prompt)
            
        elif method == "system.status":
            return {
                "server": "multimodal-media-core",
                "version": "1.0.0",
                "capabilities": [
                    "document_ocr (OCRmyPDF)",
                    "markdown_converter (MarkItDown)",
                    "speech_to_text (Whisper)",
                    "text_to_speech (Audiblez/Kokoro)",
                    "diagram_generator (DeepDiagram)"
                ]
            }
        else:
            return {"error": f"Method '{method}' not found"}

    def run_stdio_loop(self):
        sys.stderr.write("[MultimodalMediaCore] Servidor MCP ativo via stdio...\n")
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
