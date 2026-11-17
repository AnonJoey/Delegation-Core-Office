# ai-memory no delegation-core

O [ai-memory](https://github.com/akitaonrails/ai-memory) (Fabio Akita, MIT, versao 3.1.0, revisao
`584ab792` de 2026-10-16) e uma memoria de longo prazo para agentes de codigo, escrita em Rust
(cerca de 470 mil linhas). O delegation-core resolve um problema vizinho em Python. Este documento
registra o que o ai-memory faz (engenharia reversa do codigo, nao so do README), o que foi levado
para ca, o que ficou de fora e por que, e como se sabe que o porte confere com o original.

Um `git merge` e impossivel (Rust contra Python, 470 mil linhas contra um daemon MCP), entao o que
houve foi um **porte seletivo**: cada mecanismo que o delegation-core nao tinha foi lido no codigo
original, reescrito em Python e conferido contra o Rust compilado da mesma revisao.

## 1. Como o ai-memory funciona

**A fonte da verdade e uma wiki em markdown; o banco e derivado.** Cada pagina e um arquivo `.md`
com frontmatter. Um indice SQLite (FTS5 mais tabelas de entidades e de links, vetores opcionais) e
reconstruivel a qualquer momento a partir dos arquivos. A busca funde tres listas (texto, entidade,
link) por RRF e reordena.

**Hooks de ciclo de vida alimentam a memoria sem o agente pedir.** O inicio de sessao injeta um
resumo e uma passagem de bastao pendente; o fim de sessao grava observacoes, uma pagina de sessao e,
se houver, uma passagem automatica para a proxima. Tudo o que volta para o contexto vai entre
marcadores de "dado nao confiavel", porque foi escrito por outro agente.

**O esquecimento e uma formula, nao um prazo.** Cada pagina episodica tem uma retencao

```
retencao = saliencia * exp(-lambda * idade_em_dias)
         + sigma * ln(1 + leituras) * exp(-mu * dias_desde_a_ultima_leitura) * amplitude
```

com `lambda = 0,02` (meia-vida de 35 dias), `sigma = 0,6`, `mu = 0,04` e limiar de 0,20. Uma pagina
nunca lida cai abaixo do limiar em cerca de 80 dias; cada leitura a segura por mais algumas semanas.
So a camada episodica esfria: semantica, procedural e fixada ficam. Uma pagina fria nao some: vira
resumo mais a lista dos fatos duraveis minerados do texto por expressoes regulares (caminhos, URLs,
codigos de erro, identificadores), sem modelo. Uma pagina ja compactada e terminal.

**Uma passagem de bastao e um retrato tipado de "onde paramos".** Estados `aberta`, `aceita`,
`expirada`. A manual (uma pessoa deixou) vale para o projeto todo; a automatica (uma sessao acabou)
so serve a quem comeca no mesmo diretorio ou abaixo. Aceitar e um compare-and-set: de duas sessoes
que correm, so uma recebe o texto.

**A busca tem um fator de autoridade.** Um multiplicador limitado a 0,55 e 1,50, somado de tipo
(regra e decisao sobem, sessao desce), camada, fixacao e etiquetas (`canonical` sobe; `superseded`,
`historical` e `do-not-answer-from` limitam o fator por cima).

O resto (workstreams gerenciados, o laco de auto-melhoria, o perfil entre projetos, o servidor MCP
em Rust) nao tem equivalente a portar aqui.

## 2. O que foi levado

Tudo nasce **desligado** (`false` no `config.json`): cada item muda o que o agente ve ou o que o
vault guarda, e quem liga escolhe.

| Mecanismo do ai-memory | No delegation-core | Liga com |
|---|---|---|
| Retencao, salience, voto de utilidade | `envelhecimento/retencao.py`, `acessos.py` | `envelhecimento_enabled` |
| Mineracao de fatos duraveis | `envelhecimento/fatos_duraveis.py` | idem |
| Compactacao extrativa (A2) | `envelhecimento/compactacao.py` | idem |
| Varredura de esquecimento e TTL (`expires_at`) | `envelhecimento/varredura.py` (plano puro) e `envelhecimento_vault.py` (aplica) | idem; ferramenta `vault_forget_sweep` |
| Voto de utilidade | `vault_note_feedback` | idem |
| Passagem de bastao, aceitacao atomica | `passagem/` (sqlite) e `passagem_vault.py` | `passagem_enabled`; `handoff_create`, `handoff_pickup`, `handoff_list`, `handoff_cancel`; hooks de inicio e fim de sessao |
| Cerca de dado nao confiavel | `cerca_nao_confiavel.py` | usada pela passagem e pelo resumo |
| Resumo de inicio de sessao em niveis (L0, L1, L2) | `resumo_inicial/` e `resumo_vault.py` | `resumo_niveis_enabled` (hook de inicio de sessao) |
| Autoridade na busca e roteamento de pergunta de sessao | `ranqueamento/autoridade.py` e `ranqueamento_vault.py` | `autoridade_enabled`, `autoridade_forca` |

Os pacotes `envelhecimento`, `passagem`, `resumo_inicial` e `ranqueamento/autoridade.py` sao
independentes (so biblioteca padrao e `texto_bytes`), como os demais pacotes portados. A cola com o
vault fica nos modulos `*_vault.py`.

### Esquecer sem perder nada

A varredura **nunca apaga**. Uma nota fria e regravada como resumo mais fatos e `compacted: true`;
uma expirada vai para `.lixeira/<data>/` e sai do indice (`memoria.esquecer`, que ja existia). Nos dois
casos o texto inteiro fica antes no historico de versoes, e `vault_note_restore` o traz de volta.
Restaurar conta como uma leitura, para a nota nao ser compactada de novo na varredura seguinte. O
padrao de `vault_forget_sweep` e mostrar o plano (`apply=false`).

### Quais notas esfriam

Um vault de notas nao tem camada. Esfriam so as pastas de `envelhecimento_pastas` (padrao: `Sessions`,
onde estao as transcricoes e os resumos de sessao); o resto do vault conta como semantico. A validade
`expires_at:` do frontmatter vale no vault inteiro, fixada ou nao, como no original. A idade vem da
**data da nota** (`facetas.data_da_nota`: nome do arquivo, frontmatter ou mtime), e nao do mtime, porque
os passes de relink e manutencao reescrevem notas e renovariam a idade de tudo. Cada `read_note` e cada
nota devolvida por `search_vault` contam como uso.

### Configuracao

```json
{
  "envelhecimento_enabled": true,
  "envelhecimento_pastas": ["Sessions"],
  "envelhecimento_meia_vida_dias": 35,
  "envelhecimento_limiar_frio": 0.20,
  "envelhecimento_compactar": true,
  "passagem_enabled": true,
  "resumo_niveis_enabled": true,
  "resumo_niveis_orcamento": 6000,
  "autoridade_enabled": true,
  "autoridade_forca": 1.0
}
```

Reiniciar o daemon depois de mudar (as ferramentas desligadas nem aparecem no `tools/list`). Para
desfazer: voltar a chave para `false`; nada mais precisa ser revertido, e o que a varredura mudou
volta por `vault_note_restore`.

## 3. O que ficou de fora

| Item do original | Por que nao |
|---|---|
| Indice SQLite/FTS5, RRF de tres listas, vetores | O delegation-core tem busca propria (ChromaDB, lexico BM25, RRF, reordenador). Trocar nao era o objetivo. |
| Agrupar paginas frias quase iguais por DBSCAN (A3) | Pede vetores guardados por pagina; o ChromaDB daqui nao os expoe do mesmo jeito. Fica para quando houver uso real da compactacao. |
| Podar observacoes e livros-razao de eventos | O delegation-core nao tem essas tabelas. |
| Limpar lapides apos 180 dias | A `.lixeira/` e o historico de versoes ja sao a lapide, e apagar de vez nao e desfazivel. Quem quiser limpa a `.lixeira/` a mao. |
| Passagem "por turno" (a sessao renova a propria passagem a cada resposta) e checagem de sessao ocupada | Dependem da tabela de observacoes. A passagem automatica daqui nasce no fim da sessao. |
| Varios operadores com filtro de dono | Um operador so. O campo `dono` existe no banco, mas nada o preenche. |
| Workstreams, laco de auto-melhoria, perfil entre projetos, instaladores de hook | Outro produto. |

A passagem automatica nao usa modelo: o resumo e o ultimo pedido, a ultima resposta e as caixas
`- [ ]` em aberto das tres ultimas respostas, tudo ja com segredos removidos pelo redator do hook de fim
de sessao.

## 4. Diferencas de proposito em relacao ao original

- **Autoridade age sobre o posto, nao sobre a similaridade.** O fator multiplica a nota RRF
  (`1 / (60 + posicao)`), como no original, e nao o cosseno: multiplicar o cosseno deixaria 0,60 de uma
  decisao passar 0,95 de uma sessao. Mesmo pelo posto o efeito e forte (uma decisao, 1,25, alcanca uma
  sessao, 0,77, que esteja em primeiro lugar ate cerca da posicao 38). Por isso a busca le quatro vezes
  mais candidatos quando ligada, e `autoridade_forca` escala o desvio de cada fator (0,5 e metade; 0 desliga).
- **O tipo e a camada vem da pasta** (`Decisions` e decisao semantica, `Sessions` e sessao episodica),
  com etiquetas e `pinned` lidos do frontmatter.
- **Nao ha marcador de "compactada" fora da nota.** A fonte unica e o `compacted: true` do frontmatter.
  Um marcador no sqlite sobreviveria a uma restauracao e deixaria a nota restaurada imune a varredura
  para sempre; foi o que os testes de mutacao mostraram, e foi removido.
- **A marca da cerca e do delegation-core** (`delegation-core:untrusted-history`); os marcadores do
  ai-memory tambem sao neutralizados caso aparecam em texto importado.

## 5. Como se sabe que confere

As funcoes puras do ai-memory estao **copiadas sem alteracao** em `scripts/oraculo_ai_memory` (cada
arquivo cita arquivo, linhas e revisao) e compiladas num programa que le um caso por linha de JSON.
`scripts/paridade_ai_memory.py` sorteia casos desenhados para quebrar um porte e exige igualdade exata,
inclusive de numeros em ponto flutuante:

```
retencao fria sessao fatos residuo compactar trecho niveis autoridade cwd escolher
33000 de 33000 casos iguais ao original
```

`--mutacoes` injeta 25 defeitos conhecidos no porte (um sigma 1% maior, a ordem das classes de fatos,
a folga de 128 bytes, o teto de 1,5, a fronteira de componente de caminho, `splitlines` no lugar de
`lines`, a saturacao da subtracao...) e exige que a paridade os acuse: **25 de 25 pegos**. Uma paridade
que nao falha quando o porte erra nao prova nada.

Quatro diferencas de dialeto entre Rust e Python mudavam a saida e estao tratadas em `texto_bytes.py`:
o que e espaco (`White_Space` contra `isspace`, que aceita `\x1c` a `\x1f`), o que e linha (`str::lines`
mantem um `\r` solto), o que e tamanho (limites em bytes UTF-8, com corte em fronteira de caractere) e
o que e letra (`char::is_alphabetic` inclui numeros-letra e marcas que `isalpha` nao; a tabela da
diferenca, `texto_alfabetico.py`, e gerada do proprio oraculo por `scripts/gerar_alfabetico.py`).
Um quinto problema so apareceu com o binario: `serde_json` le numeros em ponto flutuante com um
arredondamento diferente a menos que se ligue `float_roundtrip`.

Alem da paridade, a cola com o vault e os hooks tem testes proprios sobre um vault falso e sqlite em
`tmp_path` (nada toca o vault ou a config reais), e os testes foram submetidos a mutacao: as mutacoes
que sobreviveram apontaram tres lacunas de teste e uma decisao de desenho (o marcador acima).

## 6. Limites conhecidos

- A varredura e **manual** (a ferramenta `vault_forget_sweep`); nao ha agendamento. Colocar na agenda do
  daemon e uma linha em `agenda_tarefas` quando houver uso real.
- A passagem automatica depende de o hook de fim de sessao estar instalado; sem ele so existe a manual.
- A autoridade nao foi medida contra um conjunto de perguntas do vault real (`aferir_busca` mede
  recuperacao, nao desempate). O efeito esta documentado e tem botao; antes de deixar ligada por padrao, medir.
- O roteamento "pergunta de sessao" e lexico (portugues, ingles e chines do original); uma pergunta
  fora desses marcadores nao e reconhecida.
