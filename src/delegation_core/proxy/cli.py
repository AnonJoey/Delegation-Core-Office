"""`delegation-core proxy env|status|run`."""

from __future__ import annotations


def cmd_proxy(args) -> int:
    from ..config import Config
    cfg = Config.load()
    url = f"http://{cfg.server_host}:{cfg.proxy_port}"
    if args.acao == "env":
        print(f"export ANTHROPIC_BASE_URL={url}")
        print(f"export OPENAI_BASE_URL={url}/v1")
        if not cfg.proxy_enabled:
            print("# proxy_enabled is false: set it to true in config.json and restart the daemon")
        return 0
    if args.acao == "status":
        import httpx
        try:
            r = httpx.get(url + "/delegation-core/proxy/health", timeout=3)
            print(f"proxy up at {url}: {r.json()}")
            return 0
        except httpx.HTTPError:
            print(f"proxy not answering at {url} (proxy_enabled={cfg.proxy_enabled})")
            return 1
    if args.acao == "run":
        import uvicorn
        from .. import livro_mcp
        from .servidor import criar_app
        print(f"proxy in the foreground at {url} (Ctrl-C stops)")
        uvicorn.run(criar_app(cfg, livro_mcp.livro(cfg)), host=cfg.server_host, port=cfg.proxy_port,
                    log_level="warning", access_log=False)
        return 0
    return 1


def registrar(sub) -> dict:
    p = sub.add_parser("proxy", help="API proxy that compresses tool outputs before they reach the model")
    p.add_argument("acao", choices=["env", "status", "run"])
    return {"proxy": cmd_proxy}
