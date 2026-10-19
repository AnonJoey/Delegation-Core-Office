# Substituto do ChromaDB: medicoes de 07/10/2026

Registro das medicoes que levaram ao indice SQLite, que entrou em producao no mesmo dia. O que o indice faz hoje e o que mudou depois esta em `indice-sqlite.md`; os numeros daqui sao os de 07/10, antes da correcao da copia da matriz de 09/10.

## Por que

O ChromaDB 1.5.9 (a ultima do PyPI) tem tres defeitos de corrupcao abertos no upstream,
sem correcao publicada: 7510 (`link_lists.bin` cresce sem limite), 7238 (SIGSEGV ao
carregar segmento corrompido) e 7678 (compactacao travada depois de SIGKILL). O m6
reproduz a queda: com um processo segurando o indice aberto, outro que abre e escreve
mais de `sync_threshold` linhas cai com SIGSEGV.

## O que o indice guarda (e o que isso diz sobre perder dados)

41.314 chunks de 16.956 documentos, 1024 dimensoes (BGE-m3). Cada chunk guarda o texto
(`chroma:document`), os metadados e o vetor.

| Origem | Documentos | Arquivo de origem existe? |
|---|---|---|
| Notas do vault (curadas) | 568 | todas |
| Notas geradas no vault | 10.023 | todas |
| Pastas externas ingeridas | 6.365 | 6.356 sim, 9 movidos para `Soteria/Deliverables/_arquivo/2026-10-02` |

Conclusao: nada existe so no indice. Os markdowns do vault sao a fonte da verdade e o
indice e derivado. Mesmo assim a migracao parte de uma exportacao neutra completa
(`m7_exportar_indice.py`: ids, textos, metadados e vetores, 41.301 chunks em 3 s), para
que re-embedar 41 mil chunks no BGE nao seja o caminho de volta.

## Interface que o codigo usa

`query` (com `where`: igualdade, `$and`, `$in`, `$ne`), `upsert`, `delete` (por `where` ou
ids), `get` paginado, `count`. Documentos guardados junto. Nada de busca por texto do
proprio Chroma.

## Candidatos

| Candidato | Versao | Situacao |
|---|---|---|
| SQLite (WAL) com vetores em BLOB e busca exata em numpy | stdlib + numpy | sem extensao nativa |
| sqlite-vec | 0.1.9 | alfa, mantenedor esporadico, forca bruta, wheels Linux, macOS e Windows |
| LanceDB | 0.40.0 | alfa, Rust, Arrow, versionado, wheels nas tres plataformas |
| DuckDB | 1.5.6 | um escritor por vez; descartado para multiprocesso |
| Qdrant | 1.19 | modo local so em Python; servidor e um processo a mais; descartado |
| FAISS, usearch, hnswlib | | so vetores, sem metadados nem ACID; exigiriam SQLite do mesmo jeito |
| Hospedados (Pinecone etc.) | | descartados: o vault tem dados de cliente e precisa funcionar offline |

## Resultados (corpus real, 41.301 x 1024)

Latencia por consulta (p50) e recall@10 contra a busca exata:

| | sem filtro | kind != generated | is_external | kind = note | disco |
|---|---|---|---|---|---|
| SQLite + numpy | 21 ms | 10 ms | 9 ms | 1 ms | 329 MB |
| sqlite-vec | 29 ms | 24 ms | 23 ms | 14 ms | 183 MB |
| LanceDB | 56 ms | 69 ms | 61 ms | 51 ms | 171 MB |

Recall 0,99 a 1,00 nos tres. O numpy e exato.

Concorrencia com 4 escritores, 1 leitor e `kill -9` aleatorio por 25 s (8 a 10 mortes):
os tres terminaram sem corrupcao, sem lote pela metade, sem duplicado e sem lote
confirmado perdido (SQLite+numpy 1.852 lotes, sqlite-vec 1.659, LanceDB 1.106).
`PRAGMA integrity_check` ok nos dois SQLite. O ChromaDB tambem passou neste teste: ele
escreve abaixo do limiar de 1000 linhas por processo que dispara o defeito, entao este
teste NAO distingue o Chroma dos candidatos.

Cenario "longevo" do m6 (um processo segura o indice aberto, outro abre, escreve 1.200
linhas e sai, 10 ciclos):

| | processos que cairam | contagem final (esperado) |
|---|---|---|
| ChromaDB 1.5.9 | 7 de 10 (SIGSEGV) | 34.300 (41.000) |
| SQLite + numpy | 0 | 53.301 (53.301) |
| sqlite-vec | 0 | 53.301 (53.301) |
| LanceDB | 0 | 53.301 (53.301), mas o handle aberto nao ve a escrita sem `checkout_latest()` |

## Recomendacao

SQLite em WAL como armazenamento de chunks (id, texto, metadados em JSON, colunas
indexadas para os filtros, vetor em BLOB) com busca exata em numpy. Razoes:
- elimina o componente nativo que corrompe, sem trocar por outro nativo em alfa;
- um arquivo, transacional, seguro para varios processos e para `kill -9`;
- exato, sem ANN para ajustar; 10 a 20 ms no corpus de hoje;
- numpy ja e dependencia (sentence-transformers).

Limites conhecidos: a matriz fica em memoria no processo que consulta (170 MB hoje) e
precisa ser recarregada quando outro processo escreve (`PRAGMA data_version`); a busca
exata cresce linearmente (ordem de 200 ms com 10 vezes o corpus, quando entraria
sqlite-vec ou quantizacao). Segunda opcao: sqlite-vec, que dispensa a matriz em memoria.

## Reproduzir

Os scripts estao em `scripts/medicoes/` e nao fazem parte do pacote. Eles precisam de `numpy`, `chromadb`, `sqlite-vec`, `lancedb` e `pyarrow`, que nao sao dependencias do delegation-core.

- `m6_hnsw_concorrencia.py` e `m6b_custo_do_sync_threshold.py`: o cenario longevo e o custo do limiar de sincronizacao do ChromaDB.
- `m7_exportar_indice.py` (exporta de uma copia do indice), `m7a_latencia_e_recall.py`, `m7b_concorrencia_e_kill9.py` e `m7c_longevo.py`: os tres candidatos.

Variaveis `EXPORT_DIR` e `BENCH_DIR`.
Cuidado: o `/tmp` costuma ser tmpfs; um escritor sem freio encheu 11 GB em 25 s.
