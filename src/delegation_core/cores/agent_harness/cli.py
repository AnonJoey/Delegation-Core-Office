import argparse
import json
import sys
from .server import AgentHarnessServer

def main():
    parser = argparse.ArgumentParser(description="Agent Harness Core - Unified Agent Skills & Tools")
    subparsers = parser.add_subparsers(dest="command")

    # Subcomando: search
    p_search = subparsers.add_parser("search", help="Buscar skills no banco indexado FTS5")
    p_search.add_argument("query", help="Termo de busca")
    p_search.add_argument("--limit", type=int, default=5, help="Max resultados")

    # Subcomando: show
    p_show = subparsers.add_parser("show", help="Exibir skill completa por ID")
    p_show.add_argument("id", type=int, help="ID da skill")

    # Subcomando: sanitize
    p_san = subparsers.add_parser("sanitize", help="Auditar e purificar texto de IA contra slop")
    p_san.add_argument("text", help="Texto para sanitizar")

    # Subcomando: inspect
    p_insp = subparsers.add_parser("inspect", help="Inspecionar arquivo de código com REA")
    p_insp.add_argument("file_path", help="Caminho do arquivo")

    # Subcomando: status
    subparsers.add_parser("status", help="Exibir telemetria do sistema")

    # Subcomando: server (MCP)
    subparsers.add_parser("server", help="Iniciar servidor MCP via stdio")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    server = AgentHarnessServer()

    if args.command == "search":
        res = server.handle_rpc("skills.search", {"query": args.query, "limit": args.limit})
        for item in res["results"]:
            print(f"[{item['id']}] ({item['source_repo']} / {item['category']}) - {item['title']}")
            print(f"    {item['snippet']}\n")

    elif args.command == "show":
        res = server.handle_rpc("skills.get", {"id": args.id})
        skill = res.get("skill")
        if skill:
            print(f"=== [{skill['id']}] {skill['title']} ({skill['source_repo']}) ===\n")
            print(skill["content"])
        else:
            print(f"Skill {args.id} nao encontrada.")

    elif args.command == "sanitize":
        audit = server.handle_rpc("sanitizer.audit", {"text": args.text})
        purified = server.handle_rpc("sanitizer.purify", {"text": args.text})
        print("--- Auditoria Anti-Slop ---")
        print(f"Score: {audit['score']} | Violacoes: {audit['total_violations']}")
        print(f"Marcadores detectados: {audit['slop_detected']}")
        print("\n--- Texto Purificado ---")
        print(purified["cleaned"])

    elif args.command == "inspect":
        res = server.handle_rpc("tools.inspect_code", {"file_path": args.file_path})
        print(json.dumps(res, indent=2))

    elif args.command == "status":
        res = server.handle_rpc("system.status", {})
        print(json.dumps(res, indent=2))

    elif args.command == "server":
        server.run_stdio_loop()

if __name__ == "__main__":
    main()
