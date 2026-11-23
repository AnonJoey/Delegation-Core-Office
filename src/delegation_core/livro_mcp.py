"""Middleware que lanca cada chamada de ferramenta no livro-caixa (pacote `livro`).

Separado do `client_tracking` de proposito: aquele responde "quem esta
conectado", este responde "o que cada ferramenta custou e entregou". Um pode
ser desligado sem o outro. `livro_enabled = false` desliga este.

Nunca derruba a chamada: medir e acessorio. O tempo e medido em volta do
`call_next`, entao inclui fila e espera, que e o que o agente de fato esperou.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from fastmcp.server.middleware import Middleware, MiddlewareContext

from .livro import LivroCaixa

logger = logging.getLogger("livro_mcp")

_LIVROS: dict[str, LivroCaixa] = {}


def livro(cfg) -> LivroCaixa | None:
    if not getattr(cfg, "livro_enabled", True):
        return None
    from .config import CONFIG_DIR

    caminho = str(Path(getattr(cfg, "livro_path", "") or CONFIG_DIR / "livro.sqlite3"))
    if caminho not in _LIVROS:
        _LIVROS[caminho] = LivroCaixa(caminho)
    return _LIVROS[caminho]


def _texto_do_resultado(resultado) -> str:
    partes = []
    for c in getattr(resultado, "content", None) or []:
        t = getattr(c, "text", None)
        if isinstance(t, str):
            partes.append(t)
    return "".join(partes)


def chars_apontados(cfg, texto: str) -> int:
    """Soma do tamanho das notas em `sources` de uma resposta JSON. 0 se nao houver."""
    try:
        d = json.loads(texto)
    except (ValueError, TypeError):
        return 0
    if not isinstance(d, dict):
        return 0
    raiz = Path(cfg.vault)
    total = 0
    for s in d.get("sources") or []:
        p = s.get("path") if isinstance(s, dict) else None
        if not p:
            continue
        try:
            total += (raiz / p).stat().st_size
        except OSError:
            continue
    return total


class LivroMiddleware(Middleware):
    def __init__(self, cfg):
        self.cfg = cfg

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        from .compressao import pool
        t0 = time.monotonic()
        erro = ""
        resultado = None
        # A ferramenta que comprime anota aqui quanto esperou na fila do pool (6.1.3).
        esperas: list = []
        marca = pool.ESPERAS.set(esperas)
        try:
            resultado = await call_next(context)
            return resultado
        except Exception as e:
            erro = type(e).__name__
            raise
        finally:
            pool.ESPERAS.reset(marca)
            try:
                self._lancar(context, resultado, time.monotonic() - t0, erro,
                             sum(esperas) if esperas else None)
            except Exception as e:  # noqa: BLE001
                logger.debug("livro nao lancou esta chamada: %s", e)

    def _lancar(self, context, resultado, segundos: float, erro: str, espera: float | None = None) -> None:
        lv = livro(self.cfg)
        if lv is None:
            return
        msg = context.message
        nome = getattr(msg, "name", "?")
        args = getattr(msg, "arguments", None) or {}
        texto = _texto_do_resultado(resultado) if resultado is not None else ""
        if not erro and texto.startswith("{") and '"error_type"' in texto[:400]:
            try:
                erro = json.loads(texto).get("error_type", "") or ""
            except ValueError:
                pass
        cliente = ""
        fctx = getattr(context, "fastmcp_context", None)
        sess = getattr(fctx, "session", None) if fctx else None
        params = getattr(sess, "client_params", None) if sess else None
        info = getattr(params, "clientInfo", None) if params else None
        if info is not None:
            cliente = getattr(info, "name", "") or ""
        lv.registrar(nome, segundos, len(json.dumps(args, ensure_ascii=False, default=str)), len(texto),
                     cliente=cliente, chars_apontados=chars_apontados(self.cfg, texto), erro=erro,
                     espera=espera)
