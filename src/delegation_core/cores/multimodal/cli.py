import argparse
import json
import sys
from .pipeline import MultimodalPipeline
from .server.mcp_server import MultimodalMCPServer

def main():
    parser = argparse.ArgumentParser(description="Multimodal Media Core - Unified Ingestion & Synthesis Engine")
    subparsers = parser.add_subparsers(dest="command")

    # Ingest: documentos ou áudios
    p_ing = subparsers.add_parser("ingest", help="Ingerir documento, PDF ou audio e converter para Markdown")
    p_ing.add_argument("file_path", help="Caminho do arquivo")

    # TTS: síntese de áudio
    p_tts = subparsers.add_parser("tts", help="Sintetizar texto em fala neural (Audiblez)")
    p_tts.add_argument("text", help="Texto a sintetizar")
    p_tts.add_argument("--out", default="speech.mp3", help="Arquivo de saida")

    # Diagram: geração de Mermaid
    p_diag = subparsers.add_parser("diagram", help="Gerar diagrama a partir de descricao (DeepDiagram)")
    p_diag.add_argument("prompt", help="Descricao do fluxo")

    # Status: telemetria
    subparsers.add_parser("status", help="Exibir capacidades do sistema unificado")

    # Server: MCP
    subparsers.add_parser("server", help="Iniciar servidor MCP via stdio")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    pipeline = MultimodalPipeline()

    if args.command == "ingest":
        res = pipeline.ingest_asset(args.file_path)
        print(json.dumps(res, indent=2))

    elif args.command == "tts":
        res = pipeline.synthesize_speech(args.text, args.out)
        print(json.dumps(res, indent=2))

    elif args.command == "diagram":
        res = pipeline.generate_diagram(args.prompt)
        print(json.dumps(res, indent=2))

    elif args.command == "status":
        srv = MultimodalMCPServer()
        print(json.dumps(srv.handle_rpc("system.status", {}), indent=2))

    elif args.command == "server":
        srv = MultimodalMCPServer()
        srv.run_stdio_loop()

if __name__ == "__main__":
    main()
