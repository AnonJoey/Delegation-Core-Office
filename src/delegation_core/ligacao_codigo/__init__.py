"""Nota ligada a codigo: o identificador citado numa nota vira no de um grafo de codigo. Pacote independente.

- `citacoes.citacoes(texto)`: identificadores distintivos entre crases
- `indice.IndiceDeCodigo`: nome -> nos, por grafo, em sqlite, refeito so quando o grafo muda
- `citacoes.ligar(texto, indice)`: qual grafo a nota discute (voto) e a que nos ela se refere
"""

from .citacoes import Alvo, citacoes, chave_da_citacao, ligar
from .indice import IndiceDeCodigo
from .mudancas import faixas_do_diff, nos_tocados

__all__ = ["Alvo", "IndiceDeCodigo", "citacoes", "chave_da_citacao", "faixas_do_diff", "ligar", "nos_tocados"]
