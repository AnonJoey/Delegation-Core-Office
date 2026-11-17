import argparse
import json
import sys
from .server.mcp_server import LocalPlatformMCPServer

def main():
    parser = argparse.ArgumentParser(description="Local Platform Core - Unified Local Ecosystem Engine")
    subparsers = parser.add_subparsers(dest="command")

    # Run agent session
    p_run = subparsers.add_parser("run", help="Executar sessao de agente com poda, travas e telemetria")
    p_run.add_argument("--prompt", default="// Analisar codigo \n def test(): pass", help="Prompt do agente")
    p_run.add_argument("--session", default="sess_42", help="ID da sessao")

    # Prune
    p_prune = subparsers.add_parser("prune", help="Comprimir contexto e podar tokens de AST/terminal")
    p_prune.add_argument("text", help="Texto a podar")

    # Hardware
    subparsers.add_parser("hardware", help="Telemetria do servidor Corsair NVMe")

    # Status
    subparsers.add_parser("status", help="Status do ecossistema")

    # Server MCP
    subparsers.add_parser("server", help="Iniciar servidor MCP via stdio")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    srv = LocalPlatformMCPServer()

    if args.command == "run":
        res = srv.handle_rpc("agent.session", {"session_id": args.session, "prompt": args.prompt})
        print(json.dumps(res, indent=2))
    elif args.command == "prune":
        res = srv.handle_rpc("prune.tokens", {"text": args.text})
        print(json.dumps(res, indent=2))
    elif args.command == "hardware":
        print(json.dumps(srv.handle_rpc("hardware.metrics", {}), indent=2))
    elif args.command == "status":
        print(json.dumps(srv.handle_rpc("system.status", {}), indent=2))
    elif args.command == "server":
        srv.run_stdio_loop()

if __name__ == "__main__":
    main()
