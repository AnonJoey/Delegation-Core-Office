"""Envelhecimento da memoria: o que vale guardar, o que compactar, o que esquecer.

Porte, para Python, do envelhecimento do ai-memory (github.com/akitaonrails/ai-memory, MIT,
Fabio Akita). O desenho esta em `docs/ai-memory.md`.

- `retencao` (funcao `pontuacao`): a formula pura (idade, uso, saliencia) e o voto de utilidade.
- `fatos_duraveis`: o que sobra de uma nota quando a prosa vai embora (caminhos, URLs, erros).
- `compactacao`: a nota compactada (resumo, fatos, rodape).

Pacote independente: nada aqui sabe o que e vault, config, indice ou MCP.
"""

from .compactacao import RODAPE, RODAPE_AI_MEMORY, compactar
from .fatos_duraveis import minerar_fatos, residuo
from .retencao import Parametros, lambda_da_meia_vida, pontuacao, saliencia_depois_do_voto

__all__ = [
    "Parametros", "RODAPE", "RODAPE_AI_MEMORY", "compactar", "lambda_da_meia_vida", "minerar_fatos",
    "pontuacao", "residuo", "saliencia_depois_do_voto",
]
