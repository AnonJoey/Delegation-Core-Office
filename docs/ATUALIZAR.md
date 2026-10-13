# Atualizar o delegation-core pelo GitHub

Quem instalou o delegation-core a partir deste repositório atualiza com um
comando. O `update` para o serviço, baixa o ramo `master`, reinstala o pacote,
renova os documentos e os hooks e sobe o serviço de volta. O vault, a
configuração e o índice não são tocados.

## O caminho curto

```
delegation-core update --check    # mostra a versão, o ramo e quantos commits faltam
delegation-core update            # atualiza
delegation-core status            # confere a versão nova
delegation-core doctor            # confere a instalação
```

Depois, reconecte o MCP (`/mcp` no Claude Code, ou reinicie o Claude Desktop) e
rode uma busca de uma nota que você conhece.

O `update` recusa rodar quando há alteração local em arquivo rastreado na pasta
de origem, para não perder trabalho. Nesse caso ele diz qual arquivo é, e a
decisão é sua.

## Pedindo ao Claude

Cole numa sessão do Claude Code na máquina que vai atualizar:

```
Atualize o delegation-core desta máquina pelo GitHub, com segurança.
Rode `delegation-core update --check` e me mostre a saída. Se o ramo não for
`master`, se o `origin` não for o repositório do delegation-core, ou se aparecer
"cannot_locate_source" ou "refused_dirty_checkout", pare e me pergunte.
Se estiver tudo certo, rode `delegation-core update`, depois `delegation-core status`
e `delegation-core doctor`, e me mostre as três saídas. Nunca use `--force`,
`--local` nem `reindex`, e nunca apague o vault nem uma pasta de índice.
```

## O índice (v0.16.0 em diante)

O índice de busca passou do ChromaDB para um arquivo SQLite. A atualização
**não troca um índice do ChromaDB que já tem dados**: ele continua em uso até
você pedir a migração. Uma instalação nova já nasce com o índice novo.

Para migrar um índice antigo que está saudável, com o serviço parado e
`pip install 'delegation-core[chroma]'` feito para ler o índice antigo:

```
delegation-core service stop
delegation-core index-migrate --ativar
delegation-core service start
delegation-core doctor
```

A migração confere linha a linha antes de trocar, e o índice antigo nunca é
apagado. Para voltar atrás, ponha `"index_backend": "chroma"` no `config.json`.
Os detalhes, o que fazer com um índice já danificado e a tabela de escala estão
em [`indice-sqlite.md`](indice-sqlite.md).

## Qual versão estou usando

`delegation-core status` mostra a versão. As mudanças de cada uma estão no
`CHANGELOG.md`, e o registro de cada implantação em `DEPLOYMENT_LOG.md`.
