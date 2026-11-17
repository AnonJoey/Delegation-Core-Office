"""
auth.py — bearer-token authentication for the HTTP transport.

Why this exists at all
----------------------
Until v0.11 delegation-core spoke MCP over stdio: the client *spawned* the
server as a child process, so "who may talk to it" was answered by process
ancestry and there was nothing to authenticate. Serving HTTP replaces that with
a listening socket, and a listening socket on loopback is reachable by every
process on the machine — including any web page open in the user's browser,
which can POST to a guessed port.

That is not hypothetical here. ``dashboard_api.py`` shipped
``Access-Control-Allow-Origin: *`` with no auth in v0.8.0, and the v0.8.1 review
recorded the consequence: any website could read and write vault and process
data through a guessed local port. The dashboard's answer was an Origin
allowlist, which works because a browser sets Origin and cannot be talked out
of it. It does *not* generalise here — a non-browser local process sets whatever
headers it likes — so this transport authenticates with a shared secret instead.

There is deliberately no unauthenticated mode. ``Config.ensure_server_token()``
generates a token on first start rather than leaving one unset, so an install
that predates HTTP transport comes up authenticated instead of coming up open.

What a token does and does not buy
----------------------------------
It separates *this* user's clients from other local processes. It is not a
defence against an attacker who can already read ``~/.delegation_core/config.json``
— at that point they have the vault path too. Keep the bind on loopback;
the token is not a licence to expose the port.
"""

from __future__ import annotations

import hmac
import logging

from fastmcp.server.auth import AccessToken, AuthProvider

logger = logging.getLogger("auth")

#: Reported as the authenticated principal. Every accepted request is the same
#: local user — the token proves "one of this user's clients", nothing finer.
LOCAL_CLIENT_ID = "delegation-core-local"



def _iguais(a: str, b: str) -> bool:
    """compare_digest em bytes: com str, um caractere nao ASCII levanta TypeError."""
    return hmac.compare_digest(a.encode("utf-8", "surrogatepass"),
                               b.encode("utf-8", "surrogatepass"))

class LocalTokenAuth(AuthProvider):
    """Accepts exactly one shared secret, presented as ``Authorization: Bearer``.

    FastMCP's ``AuthProvider`` base is a ``TokenVerifier``: returning an
    ``AccessToken`` accepts the request, returning ``None`` rejects it. No OAuth
    routes are registered — the inherited ``get_routes``/``get_well_known_routes``
    return empty lists, which is what we want for a loopback daemon with no
    authorization server behind it.
    """

    def __init__(self, token: str, base_url: str | None = None, tokens_nomeados=None):
        super().__init__(base_url=base_url)
        self._token = token or ""
        # Tokens por cliente com escopo (escopos.py): funcao que devolve
        # {nome: {"token": ..., "scope": "read"|"write"}}. Funcao, e nao dict,
        # para criar e revogar token valer sem reiniciar o daemon.
        self._nomeados = tokens_nomeados or (lambda: {})
        if not self._token:
            # Reachable only if something constructed this directly instead of
            # going through ensure_server_token(). Fail closed and say so: a
            # silent open server is the failure mode this module exists to stop.
            logger.error(
                "LocalTokenAuth built with an empty token — every request will be "
                "rejected. Generate one with Config.ensure_server_token()."
            )

    async def verify_token(self, token: str) -> AccessToken | None:
        # compare_digest over the raw strings: a plain == leaks how many leading
        # characters matched through timing. Cheap to do right, so do it right.
        if not token:
            return None
        # Em bytes: compare_digest levanta TypeError para str com caractere nao
        # ASCII, e o cabecalho e entrada de quem chama. Medido em 16/11/2026:
        # `Authorization: Bearer cafe` com acento devolvia 500 em vez de 401.
        # Vale para o token mestre e para os tokens por cliente.
        if self._token and _iguais(token, self._token):
            return AccessToken(token=token, client_id=LOCAL_CLIENT_ID, scopes=["master"])
        from .escopos import escopos_de
        try:
            nomeados = self._nomeados() or {}
        except Exception as e:  # noqa: BLE001 - config ilegivel: so o mestre passa
            logger.warning("client tokens unreadable: %s", e)
            nomeados = {}
        for nome, d in nomeados.items():
            t = (d or {}).get("token", "")
            if t and _iguais(token, t):
                return AccessToken(token=token, client_id=f"client:{nome}",
                                   scopes=escopos_de((d or {}).get("scope", "read")))
        logger.warning("Rejected an MCP request carrying an invalid bearer token")
        return None
