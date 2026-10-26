"""Rebaixa para INFO o erro que e so um cliente MCP desconectando.

Diagnostico de 26/10/2026 numa maquina macOS: 18 "Error in standalone SSE writer" e 3
"Error handling POST request" em 27 dias, todos `anyio.ClosedResourceError`, nos reinicios
e reconexoes. Quem le o log atras de falha de verdade perde tempo com eles. A excecao
continua no registro, com o traceback; so o nivel muda. Qualquer outra excecao nos mesmos
registros segue como ERROR.
"""
from __future__ import annotations

import logging

#: Excecoes que o anyio levanta quando o outro lado do fluxo ja foi fechado.
EXCECOES_DE_DESCONEXAO = ("ClosedResourceError", "BrokenResourceError", "EndOfStream")


class DesconexaoDeCliente(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.ERROR and record.exc_info and record.exc_info[0] is not None:
            if record.exc_info[0].__name__ in EXCECOES_DE_DESCONEXAO:
                record.levelno = logging.INFO
                record.levelname = "INFO"
        return True


def instalar(logger: logging.Logger | None = None) -> None:
    """Poe o filtro em cada handler do logger raiz (filtro de logger nao pega o dos filhos)."""
    raiz = logger or logging.getLogger()
    for handler in raiz.handlers:
        if not any(isinstance(f, DesconexaoDeCliente) for f in handler.filters):
            handler.addFilter(DesconexaoDeCliente())
