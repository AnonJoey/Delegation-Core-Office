# Evals da busca

Um conjunto de 40 notas e 40 perguntas, com a nota esperada de cada uma, roda a cada `pytest` e mede os três modos de busca do índice SQLite. O número aparece no log do CI e **cai quando a busca piora**.

## O que mede

| Modo | O que é |
|---|---|
| `vetorial` | Busca exata por cosseno sobre os vetores |
| `lexical` | BM25 sobre trigramas (FTS5) |
| `hibrida` | Fusão RRF entre os dois |

Métricas por modo: acerto na 1ª posição (`hit@1`), no top 3 (`hit@3`), no top 5 (`hit@5`) e MRR (média do inverso da posição da nota esperada).

Medida de 08/10/2026, na criação:

| modo | hit@1 | hit@3 | hit@5 | mrr |
|---|---:|---:|---:|---:|
| vetorial | 0,850 | 0,925 | 0,950 | 0,894 |
| lexical | 0,875 | 0,975 | 0,975 | 0,917 |
| hibrida | 0,925 | 0,950 | 1,000 | 0,950 |

## O que NÃO mede

A qualidade do BGE-M3. O embedder do teste é um saco de palavras determinístico, porque o CI roda offline e sem baixar modelo. O conjunto pega regressão do índice, do filtro, da fusão e da busca de texto. Trocar o modelo de embeddings pede outra avaliação, com o modelo real, sobre o mesmo corpus.

## Como a guarda funciona

`tests/evals_busca/baseline.json` guarda as métricas medidas. O teste falha se qualquer métrica de qualquer modo ficar abaixo do valor guardado (tolerância de 0,0005). Melhorar não falha.

Depois de uma melhora de verdade:

```bash
pytest tests/test_evals_busca.py -s --atualizar-baseline-evals
```

regrava o arquivo; explique a mudança no commit.

## Prova de que a guarda enxerga

Três regressões provocadas à mão no código de busca, cada uma derrubou o teste:

| Regressão provocada | Efeito medido |
|---|---|
| `hibrida` ignora a busca lexical | `hit@1` de `hibrida` de 0,925 para 0,850 |
| BM25 devolve a ordem invertida | `hit@1` de `lexical` de 0,875 para 0,125 |
| Vetorial pega os piores resultados | `hit@1` de `vetorial` de 0,850 para 0,000 |

Um teste de sensibilidade também garante que inverter a ordem de qualquer modo derruba o MRR em mais de 0,1.

## Para ampliar

- Acrescentar notas e perguntas em `tests/evals_busca/corpus.json` (uma pergunta por nota, para uma regressão não se esconder atrás de outra). Regravar a linha de base.
- Um conjunto com o modelo real, rodando fora do CI, sobre o mesmo corpus, para medir o BGE-M3 e comparar com este.
