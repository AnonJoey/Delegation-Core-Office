"""O servidor HTTP do proxy: Starlette + uvicorn numa thread do daemon, httpx para o provedor."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time

logger = logging.getLogger("proxy")

#: Cabecalhos que nao atravessam um proxy (RFC 9110) e os que o httpx recalcula.
_SALTO = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer",
          "transfer-encoding", "upgrade", "host", "content-length"}


#: Caminhos da API OpenAI; o resto vai para a Anthropic.
_OPENAI = ("/v1/chat/completions", "/v1/responses", "/v1/completions", "/v1/embeddings")


def _upstream(cfg, caminho: str) -> str:
    if caminho.startswith(_OPENAI):
        return (getattr(cfg, "proxy_upstream_openai", "") or "https://api.openai.com").rstrip("/")
    return (getattr(cfg, "proxy_upstream_anthropic", "") or "https://api.anthropic.com").rstrip("/")


def _pelo_pool(laco, esperas: list):
    """A compressao do proxy pelo pool do daemon, na classe interativa (6.1.3).

    `reescrever` roda numa thread (as funcoes de reescrita sao sincronas) e chama isto para cada
    resultado de ferramenta. A chamada volta ao laco do proxy, entra no portao unico do daemon com
    prioridade INTERATIVA e espera o resultado. Antes, o proxy chamava o roteador direto naquela
    thread: segurava o GIL do daemon e nao passava pela fila. O Kompress, quando entra, roda no
    processo do daemon, onde o modelo fica carregado uma vez so."""
    from ..compressao import pool

    def comprimir(texto: str) -> dict:
        async def uma():
            pool.ESPERAS.set(esperas)
            return await pool.comprimir(texto, "", "auto", 1.0, prioridade=pool.INTERATIVA)
        return asyncio.run_coroutine_threadsafe(uma(), laco).result()

    return comprimir


def criar_app(cfg, livro=None, cliente_http=None):
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse, StreamingResponse
    from starlette.routing import Route

    import httpx

    from .reescrita import reescrever

    http = cliente_http or httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=30.0))
    minimo = int(getattr(cfg, "proxy_min_chars", 2000))
    dedup = bool(getattr(cfg, "proxy_cross_turn_dedup", False))
    leitura = bool(getattr(cfg, "proxy_read_lifecycle", False))
    superseded = bool(getattr(cfg, "proxy_read_superseded", False))

    async def saude(_req: Request):
        return JSONResponse({"status": "ok", "service": "delegation-core proxy"})

    async def repassar(req: Request):
        caminho = req.url.path
        t0 = time.monotonic()
        corpo = await req.body()
        rel = None
        espera = 0.0
        if req.method == "POST" and corpo and "json" in (req.headers.get("content-type") or ""):
            try:
                dados = json.loads(corpo)
            except ValueError:
                dados = None
            if isinstance(dados, dict):
                try:
                    esperas: list = []
                    comprimir = _pelo_pool(asyncio.get_running_loop(), esperas)
                    novo, rel = await asyncio.to_thread(reescrever, caminho, dados, minimo, dedup, leitura, superseded,
                                                        comprimir)
                    espera = sum(esperas)
                    if rel.comprimidos or rel.trechos_dedup or rel.leituras_obsoletas:
                        corpo = json.dumps(novo, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                except Exception as e:  # noqa: BLE001 - comprimir e acessorio: falhou, vai o original
                    logger.warning("proxy: compression skipped (%s)", type(e).__name__)
                    rel = None
        cabecalhos = [(k, v) for k, v in req.headers.items() if k.lower() not in _SALTO]
        destino = _upstream(cfg, caminho) + caminho + (f"?{req.url.query}" if req.url.query else "")
        pedido = http.build_request(req.method, destino, headers=cabecalhos, content=corpo)
        try:
            resp = await http.send(pedido, stream=True)
        except httpx.HTTPError as e:
            return JSONResponse({"type": "error", "error": {"type": "proxy_upstream_error",
                                                             "message": f"delegation-core proxy could not reach the provider: {type(e).__name__}"}},
                                status_code=502)
        if rel is not None and livro is not None and rel.blocos:
            try:
                livro.registrar(f"proxy:{rel.formato}", time.monotonic() - t0, rel.chars_antes, rel.chars_depois,
                                cliente=req.headers.get("user-agent", "")[:60], espera=espera)
            except Exception:  # noqa: BLE001
                pass
        if rel is not None and (rel.comprimidos or rel.trechos_dedup or rel.leituras_obsoletas):
            logger.info("proxy %s: %d of %d tool outputs compressed, %d spans folded across turns, %d stale reads",
                        rel.formato, rel.comprimidos, rel.blocos, rel.trechos_dedup, rel.leituras_obsoletas)
        saida_cab = [(k, v) for k, v in resp.headers.multi_items() if k.lower() not in _SALTO]

        async def bytes_da_resposta():
            try:
                async for pedaco in resp.aiter_raw():
                    yield pedaco
            finally:
                await resp.aclose()
        r = StreamingResponse(bytes_da_resposta(), status_code=resp.status_code)
        r.raw_headers = [(k.encode("latin-1"), v.encode("latin-1")) for k, v in saida_cab]
        return r

    rotas = [Route("/delegation-core/proxy/health", saude, methods=["GET"]),
             Route("/{caminho:path}", repassar, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])]
    return Starlette(routes=rotas)


def servir_em_thread(cfg, livro=None, host: str = "127.0.0.1", porta: int | None = None):
    """Sobe o proxy numa thread do daemon. Devolve o uvicorn.Server (para parar)."""
    import uvicorn
    porta = porta if porta is not None else int(getattr(cfg, "proxy_port", 8789))
    servidor = uvicorn.Server(uvicorn.Config(criar_app(cfg, livro), host=host, port=porta,
                                             log_level="warning", access_log=False, lifespan="off"))
    servidor.install_signal_handlers = lambda: None
    threading.Thread(target=servidor.run, daemon=True, name="api-proxy").start()
    logger.info("API proxy listening on http://%s:%d", host, porta)
    return servidor
