import argparse
import json
import sys
from .server.mcp_server import OrchestrationMCPServer

def main():
    parser = argparse.ArgumentParser(description="Orchestration Core - Dagu + LangWatch + Multica + Pullfrog + Fleetbase Unified")
    subparsers = parser.add_subparsers(dest="command")

    # Run workflow demo
    p_run = subparsers.add_parser("run", help="Executar workflow DAG com telemetria síncrona")
    p_run.add_argument("--title", default="Pipeline-CI-Agent", help="Titulo do workflow")

    # CI check
    p_ci = subparsers.add_parser("ci", help="Verificar integridade de PR com Pullfrog runner")
    p_ci.add_argument("--pr", type=int, default=1, help="Numero do PR")

    # Status
    subparsers.add_parser("status", help="Status dos motores integrados")

    # Server MCP
    subparsers.add_parser("server", help="Iniciar servidor MCP via stdio")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    srv = OrchestrationMCPServer()

    if args.command == "run":
        res = srv.handle_rpc("workflow.run_demo", {"title": args.title})
        print(json.dumps(res, indent=2))
    elif args.command == "ci":
        res = srv.handle_rpc("ci.verify_pr", {"pr_id": args.pr})
        print(json.dumps(res, indent=2))
    elif args.command == "status":
        print(json.dumps(srv.handle_rpc("system.status", {}), indent=2))
    elif args.command == "server":
        srv.run_stdio_loop()

if __name__ == "__main__":
    main()
