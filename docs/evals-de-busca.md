# Evals da busca

Um conjunto de 40 notas e 40 perguntas, com a nota esperada de cada uma, roda a cada `pytest` e mede os três modos de busca do índice SQLite. O número aparece no log do CI e **cai quando a busca piora**.

## O que mede

| Modo | O que é |
|---|---|
| `vetorial` | Busca exata por cosseno sobre os vetores |
| `lexical` | BM25 sobre trigramas (FTS5) |
| `hibrida` | Fusão RRF entre os dois |

Métricas por modo: acerto na 1ª posição (`hit@1`), no top 3 (`hit@3`), no top 5 (`hit@5`) e MRR (média do inverso da posição da nota esperada).

Medida de 08/10/2026, depois de remover empates (ver "Armadilha: empates" abaixo):

| modo | hit@1 | hit@3 | hit@5 | mrr |
|---|---:|---:|---:|---:|
| vetorial | 0,975 | 1,000 | 1,000 | 0,983 |
| lexical | 0,925 | 1,000 | 1,000 | 0,958 |
| hibrida | 1,000 | 1,000 | 1,000 | 1,000 |

**O conjunto está fácil.** A híbrida acerta tudo, então uma melhora nela não aparece, e uma queda pequena só aparece como uma pergunta a menos. Para a busca real do delegation-core vale ampliar com perguntas mais difíceis, desde que elas não criem empates (abaixo).

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

Regressões provocadas à mão no código de busca, cada uma derrubou o teste:

| Regressão provocada | Efeito medido |
|---|---|
| `hibrida` ignora a busca lexical | `hit@1` de `hibrida` de 1,000 para 0,975 (queda pequena: o conjunto está fácil) |
| BM25 devolve a ordem invertida | `hit@1` de `lexical` de 0,925 para 0,100 |
| Vetorial pega os piores resultados | `hit@1` de `vetorial` de 0,975 para 0,000 |

Um teste de sensibilidade também garante que inverter a ordem de qualquer modo derruba o MRR em mais de 0,1.

## Armadilha: empates

A primeira versão deste conjunto tinha três perguntas em que a nota esperada empatava em pontuação com outra. Empate se desfaz pela ordem em que as notas entraram no índice, e isso pode mudar de sistema operacional para sistema operacional: o CI do macOS ou do Windows falharia sem regressão nenhuma. Foi achado embaralhando a ordem de inserção. Duas causas: colisões de hash no embedder de teste (512 dimensões, hoje 8.192) e perguntas com pouca sobreposição de palavras. Hoje `test_o_resultado_nao_depende_da_ordem_de_insercao` embaralha a ordem com cinco sementes e exige o mesmo resultado; ao acrescentar perguntas, esse teste avisa se alguma criar empate.

## Para ampliar

- Acrescentar notas e perguntas em `tests/evals_busca/corpus.json` (uma pergunta por nota, para uma regressão não se esconder atrás de outra). Regravar a linha de base.
- Um conjunto com o modelo real, rodando fora do CI, sobre o mesmo corpus, para medir o BGE-M3 e comparar com este.
