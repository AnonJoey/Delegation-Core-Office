"""Referencias: caminho citado numa nota que nao existe mais na maquina. Pacote independente.

- `caminhos.extrair(texto)`: os caminhos absolutos citados entre crases
- `caminhos.verificar(refs, existe, localizar)`: quais morreram, e onde o
  arquivo com o mesmo nome esta agora (a busca por nome e injetada)
"""

from .caminhos import Referencia, extrair, verificar

__all__ = ["Referencia", "extrair", "verificar"]
