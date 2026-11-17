"""Passagem de bastao entre agentes: o que o proximo agente precisa saber, entregue uma vez so.

Porte, para Python, do protocolo de handoff do ai-memory (github.com/akitaonrails/ai-memory, MIT,
Fabio Akita). Uma passagem e um retrato tipado de "onde paramos": criada quando uma sessao acaba
(automatica) ou por uma pessoa (manual), aceita pela proxima sessao no mesmo projeto, e aceita
exatamente uma vez.

- `caminhos`: comparar diretorios de trabalho e escolher qual passagem entregar.
- `armazem`: a tabela em sqlite, com a aceitacao atomica.
- `texto`: como a passagem aparece para quem a recebe, dentro da cerca de texto nao confiavel.

Pacote independente: so a biblioteca padrao.
"""

from .caminhos import Candidata, casa_com_cwd, cwd_dentro, escolher, normalizar_cwd

__all__ = ["Candidata", "casa_com_cwd", "cwd_dentro", "escolher", "normalizar_cwd"]
