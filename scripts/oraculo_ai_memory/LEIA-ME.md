# Oraculo do ai-memory

Um programa em Rust que roda, nos mesmos casos, as funcoes puras do
[ai-memory](https://github.com/akitaonrails/ai-memory) (MIT, Fabio Akita) que o delegation-core portou
para Python. Serve de gabarito: `scripts/paridade_ai_memory.py` sorteia os casos, roda este binario e o
porte, e exige resultado identico (numeros em ponto flutuante inclusive, bit a bit).

Nao faz parte do pacote instalado e nao e executado em producao.

## Construir

```
cd scripts/oraculo_ai_memory
cargo +1.95 build --release
```

(`AI_MEMORY_ORACULO` aponta o script de paridade para outro binario.) `target/` nao e versionado.

## O que ha aqui

`src/*.rs` sao **copias literais** de trechos do ai-memory na revisao `584ab792` (2026-10-16). O cabecalho de
cada arquivo diz de qual arquivo e de quais linhas. A unica diferenca em relacao ao original e o travessao dos
comentarios, que virou hifen (regra de escrita deste projeto); nenhuma linha de codigo mudou. `shim_core/` e uma casca minima dos tipos do
`ai-memory-core` que esse codigo toca (`Tier`, `FeedbackKind`, `OwnerFilter`, `Handoff`, `PageId`,
`PagePath`): mesmos nomes e campos, so o que as funcoes copiadas usam. `src/main.rs` e o unico arquivo
escrito aqui: le uma linha de JSON por caso, chama a funcao original e escreve o resultado.

| operacao | funcao original |
|---|---|
| `retencao`, `salience`, `lambda` | `retention_score_with_breadth`, `salience_after_feedback`, `lambda_from_half_life_days` |
| `fria` | `cold_entry_for`, `is_decayable` |
| `tokens`, `residuo` | `mine_keep_tokens`, `mine_residue_tokens` |
| `compactar` | `build_compacted_markdown` |
| `trecho`, `prosa`, `meta`, `truncar` | `excerpt_from_page`, `leading_prose`, `is_metadata_field`, `truncate_utf8_bytes` |
| `niveis` | `assign_tiers` |
| `autoridade`, `rank`, `limite` | `PageAuthority::from_stored`, `apply_rank_multiplier`, `authority_candidate_limit` |
| `sessao` | `is_session_recall_query` |
| `cwd_normalizar`, `cwd_dentro`, `casa`, `chave`, `escolher` | `normalize_cwd`, `cwd_within`, `auto_handoff_matches_cwd`, `handoff_selection_key`, `prefer_handoff` |
| `alfabeticos` | `char::is_alphabetic` (gera `src/delegation_core/texto_alfabetico.py`, ver `scripts/gerar_alfabetico.py`) |

## Rodar a paridade

```
python scripts/paridade_ai_memory.py -n 3000 -v          # todos os grupos
python scripts/paridade_ai_memory.py --so fria,sessao     # alguns
python scripts/paridade_ai_memory.py --mutacoes -n 3000   # injeta defeitos no porte e exige que a paridade os acuse
```

`--mutacoes` existe porque uma paridade que nao falha quando o porte erra nao prova nada.

## Quando o ai-memory mudar

Baixe a revisao nova, refaca as copias (as linhas citadas nos cabecalhos mudam), recompile e rode a
paridade. Uma diferenca nova e um comportamento que o original mudou: ou o porte acompanha, ou a
diferenca fica documentada em `docs/ai-memory.md`.
