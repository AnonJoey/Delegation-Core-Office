"""Sonho: o que o vault lembra, e o que nele se contradiz. Pacote independente.

- `recordacao.RegistroDeRecordacao`: o que a busca devolveu, para qual pergunta
- `contradicao`: o modelo local julga se uma nota nova contradiz, atualiza ou
  repete uma antiga (a funcao que pergunta ao modelo e injetada)
"""

from .achados import RegistroDeAchados
from .recordacao import RegistroDeRecordacao

__all__ = ["RegistroDeAchados", "RegistroDeRecordacao"]
