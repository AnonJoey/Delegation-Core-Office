"""O resumo de inicio de sessao em niveis: o trecho de cada nota fixa e quanto de cada uma cabe.

Porte, para Python, do resumo em camadas do ai-memory (github.com/akitaonrails/ai-memory, MIT,
Fabio Akita).

- `trecho`: o L0 e o L1 de uma nota, extrativos.
- `niveis`: a conta de cobertura primeiro, que decide a profundidade de cada nota no orcamento.

Pacote independente: so a biblioteca padrao.
"""

from .niveis import CustoDaNota, Nivel, Orcamento, Plano, atribuir_niveis
from .trecho import Trecho, trecho_da_nota

__all__ = ["CustoDaNota", "Nivel", "Orcamento", "Plano", "Trecho", "atribuir_niveis", "trecho_da_nota"]
