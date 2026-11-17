"""Fatos duraveis: o que uma nota afirma sobre uma coisa, com fonte e data. Pacote independente.

- `extracao.extrair(texto, perguntar)`: o modelo (injetado) lista fatos; so
  fica o fato cujo valor aparece no texto da nota
- `armazem.ArmazemDeFatos`: guarda por nota, responde por sujeito e atributo
  com o historico de valores, e aponta onde notas divergem
"""

from .armazem import ArmazemDeFatos
from .extracao import Fato, extrair, normalizar

__all__ = ["ArmazemDeFatos", "Fato", "extrair", "normalizar"]
