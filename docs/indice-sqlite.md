# Indice SQLite (no lugar do ChromaDB)

## Para que serve

O ChromaDB 1.5.9, a ultima versao do PyPI, tem tres defeitos de corrupcao abertos no
upstream (7510, 7238, 7678) e nenhuma correcao publicada. Por dentro, ele guarda o
texto e os metadados no SQLite e os vetores em arquivos HNSW separados
(`data_level0.bin`, `link_lists.bin`, `index_metadata.pickle`): dois repositorios sem
atomicidade entre si, e e dai que saem as linhas fantasma e o SIGSEGV. O indice SQLite
guarda texto, metadados e vetor na mesma transacao, e a busca e exata em numpy.

Medicoes completas em `docs/substituto-do-chromadb.md` (branch `feat/fila-operacoes`).

## Qual indice esta em uso

`index_backend` no `config.json`: `sqlite`, `chroma` ou vazio. Vazio decide pelo que existe
em disco: indice SQLite presente -> sqlite; so indice do Chroma -> chroma (um indice com
dados nunca e trocado sozinho por um vazio); nada -> sqlite, que e o de uma instalacao nova.
O `chromadb` e um extra (`pip install 'delegation-core[chroma]'`), necessario so para ler um
indice antigo e migrar; o caminho de busca e escrita do SQLite funciona sem ele.

## Como usar

```
delegation-core service stop                    # o daemon segura o indice do Chroma aberto
delegation-core index-migrate                   # exporta, importa, verifica e so entao troca a pasta
delegation-core index-compare                   # mesmas consultas nos dois indices
delegation-core index-migrate --ativar          # idem, e define index_backend = sqlite
delegation-core service start
```

- `index_backend` no `config.json`: `"chroma"` (padrao) ou `"sqlite"`. O indice novo fica em
  `<vault>/.indice_sqlite/indice.db`, ao lado do `.chroma_bge`, que **nao e tocado**.
- Voltar: `index_backend: "chroma"` e reiniciar. O que foi escrito depois da troca nao
  existe no Chroma; `delegation-core reindex --force` o reconstroi dos markdowns.
- A exportacao neutra (JSONL e `.npy`) fica em `~/.delegation_core/migracao/<data>/`. Pode
  apagar depois de validar.
- Se o Chroma nem abrir, `index-migrate` falha com a causa e nada muda; o caminho e
  `index_backend: sqlite` e `reindex --force`, que reconstroi o indice dos markdowns.
- Um indice SQLite ilegivel vai para quarentena (`.indice_sqlite-danificado-*`, nunca apagado)
  e o daemon o reconstroi dos markdowns e das fontes ingeridas.
- `index-migrate` sem `--ativar` fixa `index_backend: chroma`, para o indice novo nao ser
  assumido sem ninguem pedir.

## O que a migracao garante

Para cada colecao: mesma contagem, mesmos ids na mesma ordem, texto e metadados iguais,
vetores iguais bit a bit, `PRAGMA integrity_check` ok, e as consultas vizinhas iguais a
busca exata sobre a matriz exportada. Qualquer diferenca aborta antes de trocar a pasta.

## O que a fachada acrescenta ao ChromaDB

- `where_document` (`$contains`, `$not_contains`, `$and`, `$or`) por FTS5 trigram.
- `buscar_texto` (BM25) e `hibrida` (fusao RRF) com o mesmo `where` da busca vetorial.
- `backup(destino)`: instantaneo transacional pela API de backup do SQLite.
- `verificar()`: `PRAGMA integrity_check`.
- Atualizacao entre processos pelo registro de mudancas (`mudancas`), sem reabrir cliente.

## Limites

### Escala: o que foi medido

A busca exata guarda a matriz inteira de vetores em memoria, no daemon e em todo processo que abre o indice. Medido em 09/10/2026 numa maquina de 24 nucleos, vetores de 1024 dimensoes (os do BGE-M3), trechos com cerca de 600 caracteres de texto, 200 consultas por modo, v0.16.0 com a correcao de copia descrita abaixo:

| Trechos | Disco | Abertura a frio | Memoria depois de abrir | Busca vetorial p50 / p95 | Busca lexical (BM25) p50 / p95 | Hibrida p50 / p95 |
|---:|---:|---:|---:|---:|---:|---:|
| 41 mil | 0,33 GB | 0,3 s | 0,28 GB | 3,0 / 5,7 ms | 22 / 56 ms | 43 / 81 ms |
| 400 mil | 2,9 GB | 4,4 s | 1,9 GB | 26,6 / 26,9 ms | 206 / 521 ms | 283 / 596 ms |

(Com 100 mil e 200 mil trechos, medidos antes da correcao, a memoria foi de 0,50 e 0,95 GB e a abertura a frio de 1,7 e 3,1 s: cresce em linha reta.)

- **O indice de producao desta maquina (41,6 mil trechos) esta muito abaixo de qualquer limite.**
- **A busca lexical e a que mais pesa em escala:** com 400 mil trechos leva 206 ms no p50, contra 27 ms da vetorial. A hibrida soma as duas.
- O `doctor` avisa a partir de 500 mil trechos (cerca de 2 GB de matriz por processo), com estes numeros. Alem de mais ou menos 1 milhao, as saidas sao quantizar os vetores ou usar sqlite-vec.
- Os numeros dependem da maquina: a medida de memoria e de abertura vale para qualquer uma; a de latencia, nao.

### A copia da matriz a cada consulta (corrigida)

Ate a v0.16.0 a consulta fazia `matriz[idx] @ q`, e indexar uma matriz com um vetor de indices **copia as linhas escolhidas**. Com 41 mil trechos eram cerca de 170 MB copiados por busca; com 400 mil, 1,6 GB, e a busca sem filtro (que escolhe todas as linhas) era mais lenta que a com filtro. Agora a pontuacao e calculada sobre a matriz inteira, sem copia, e so depois se escolhem as linhas permitidas. Mesmo resultado em 900 consultas (0 ids e 0 distancias diferentes); busca vetorial de 180 ms para 27 ms no p50 com 400 mil trechos, e pico de memoria de 3,4 para 2,3 GB. O teste `tests/test_indice_sqlite_escala.py` falha se a consulta voltar a alocar uma fracao relevante da matriz.

### Outros limites

- O embedder (`EmbedderSentenceTransformer`) e proprio e gera vetores identicos aos do antigo; nada do caminho de busca e escrita importa o `chromadb`.
- Um sqlite sem FTS5 trigram (antes da 3.34) desliga `where_document` e a busca de texto; o resto funciona.
