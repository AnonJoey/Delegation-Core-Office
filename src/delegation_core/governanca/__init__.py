"""Governanca de ferramentas: politica por cliente, aprovacao humana e limite de taxa.

Trazido do Paperclip (`mcp-governance`): toda ferramenta tem uma classe
(`read`, `write`, `destructive`) e cada cliente pode ter, por ferramenta ou por
classe, uma politica `allow`, `block`, `require_approval` ou `rate_limit:N/S`.

O escopo do token (`escopos.py`) continua decidindo PRIMEIRO o que um token pode;
a politica aqui so restringe mais. Sem `tool_policies` no config, nada muda.

A aprovacao e humana de proposito: nao ha ferramenta MCP que aprove. O agente
recebe o id do pedido, a pessoa roda `delegation-core approvals approve <id>` e
o agente repete a mesma chamada, com os mesmos argumentos, uma vez.
"""

from .politica import (
    ACOES_VALIDAS, CLASSES, DESTRUTIVAS, classe_de, politica_efetiva, validar_politicas,
)
from .aprovacoes import Aprovacoes
from .taxa import LimiteDeTaxa

__all__ = [
    "ACOES_VALIDAS", "CLASSES", "DESTRUTIVAS", "Aprovacoes", "LimiteDeTaxa",
    "classe_de", "politica_efetiva", "validar_politicas",
]
