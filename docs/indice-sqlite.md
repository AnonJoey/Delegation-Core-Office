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

- A matriz fica em memoria no processo que consulta (170 MB com 41 mil chunks). A busca
  exata cresce linearmente; com ordem de 10 vezes o corpus, quantizar ou usar sqlite-vec.
- O embedder (`EmbedderSentenceTransformer`) e proprio e gera vetores identicos aos do
  antigo; nada do caminho de busca e escrita importa o `chromadb`.
- Um sqlite sem FTS5 trigram (antes da 3.34) desliga `where_document` e a busca de texto;
  o resto funciona.
