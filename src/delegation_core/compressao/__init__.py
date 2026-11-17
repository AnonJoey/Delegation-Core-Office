"""Compressores do Headroom (headroomlabs-ai/headroom, Apache 2.0), portados de Rust.

O Headroom comprime o que um agente le antes de chegar ao modelo. No pacote
publicado, os algoritmos moram num modulo Rust compilado (`headroom._core`) e o
Python so os embrulha; por isso o porte aqui e do Rust
(`crates/headroom-core/src/transforms/`), arquivo por arquivo, e a prova de
fidelidade e diferencial: o `headroom._core` 0.39.1 de verdade como oraculo
(`scripts/paridade_headroom.py`).

- `adaptativo.py`: `compute_optimal_k` (quantos itens manter, pelo joelho da
  curva de bigramas unicos, com simhash e checagem por zlib).
- `logs.py`: LogCompressor (saida de build e teste: pytest, npm, cargo, jest,
  make), com o detector de stack trace por linguagem.
- `ccr.py`: a guarda reversivel do Headroom (CCR): o original fica guardado
  e o texto comprimido termina com `Retrieve more: hash=<chave>`.
"""
