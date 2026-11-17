"""O middleware que aplica a politica a cada chamada de ferramenta.

Roda depois do EscopoMiddleware: um token de leitura ja foi recusado la, e aqui
so se restringe mais. Le `tool_policies` do config.json a cada chamada pelo
mesmo cache por mtime dos tokens, entao mudar a politica nao pede reinicio.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastmcp.server.middleware import Middleware

from .aprovacoes import Aprovacoes
from .politica import ler_taxa, politica_efetiva
from .taxa import LimiteDeTaxa

_CACHE: dict = {}


def ler_politicas(caminho_config) -> dict:
    p = Path(caminho_config)
    try:
        m = p.stat().st_mtime_ns
    except OSError:
        return {}
    if _CACHE.get("m") != m:
        try:
            _CACHE["p"] = dict(json.loads(p.read_text(encoding="utf-8")).get("tool_policies") or {})
        except (OSError, ValueError, TypeError):
            _CACHE["p"] = {}
        _CACHE["m"] = m
    return _CACHE["p"]


def nome_do_cliente() -> str:
    """O nome do token nomeado, se houver; senao o clientInfo da sessao MCP."""
    try:
        from fastmcp.server.dependencies import get_access_token
        tok = get_access_token()
    except Exception:  # noqa: BLE001 - sem contexto de auth (stdio)
        tok = None
    cid = getattr(tok, "client_id", "") or ""
    if cid.startswith("client:"):
        return cid.split(":", 1)[1]
    from ..client_tracking import current_client_name
    return current_client_name()


class PoliticaMiddleware(Middleware):
    def __init__(self, caminho_config, aprovacoes: Aprovacoes, taxa: LimiteDeTaxa | None = None,
                 cliente=nome_do_cliente):
        self.caminho_config = caminho_config
        self.aprovacoes = aprovacoes
        self.taxa = taxa or LimiteDeTaxa()
        self._cliente = cliente

    def decidir(self, cliente: str, ferramenta: str, argumentos: dict | None) -> str | None:
        """None deixa passar; um texto e o motivo da recusa."""
        acao, origem = politica_efetiva(ler_politicas(self.caminho_config), cliente, ferramenta)
        if acao == "allow":
            return None
        if acao == "block":
            return (f"policy_blocked: '{ferramenta}' is blocked for client '{cliente}' "
                    f"by {origem}.")
        taxa = ler_taxa(acao)
        if taxa:
            espera = self.taxa.tentar(cliente, ferramenta, *taxa)
            if espera:
                return (f"rate_limited: '{ferramenta}' allows {taxa[0]} calls per {taxa[1]}s for "
                        f"client '{cliente}' ({origem}). Retry in {espera:.0f}s.")
            return None
        ok, pedido = self.aprovacoes.consumir_ou_pedir(cliente, ferramenta, argumentos)
        if ok:
            return None
        return (f"approval_required: '{ferramenta}' needs a human approval for client "
                f"'{cliente}' ({origem}). Request {pedido['id']} is pending. Ask the user to run "
                f"`delegation-core approvals approve {pedido['id']}`, then repeat this exact call "
                f"with the same arguments. The approval is single-use and expires {pedido['expires']}.")

    async def on_call_tool(self, context, call_next):
        msg = context.message
        motivo = self.decidir(self._cliente(), getattr(msg, "name", ""), getattr(msg, "arguments", None))
        if motivo:
            from fastmcp.exceptions import ToolError
            raise ToolError(motivo)
        return await call_next(context)
