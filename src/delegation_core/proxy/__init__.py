"""Proxy de API do delegation-core: o proxy do Headroom, fundido ao produto.

O agente (Claude Code, Codex...) aponta a URL da API para este proxy
(`ANTHROPIC_BASE_URL=http://127.0.0.1:8789`); cada requisicao chega aqui, os
resultados de ferramenta grandes passam pelos compressores do delegation-core
(`compressao.roteador`: diff, busca, log, SmartCrusher, Kompress, sem perda) e
a requisicao segue para o provedor. A resposta volta byte a byte, sem
modificacao, inclusive em streaming.

O que faz disso um merge de produtos, e nao um segundo programa ao lado:
- roda dentro do daemon, como o painel: mesmo processo, mesmo `config.json`,
  mesmo servico; desligado por padrao (`proxy_enabled`), porta 8789;
- o original de cada corte vai para a mesma guarda CCR, e o modelo recupera
  pelo `recall_output` do MCP do delegation-core. O Headroom injeta uma
  ferramenta propria de recuperacao na requisicao; aqui nao e preciso;
- a economia de cada requisicao entra no livro-caixa (`usage_report`), ao
  lado do uso das ferramentas, e `proxy_stats` resume;
- a compressao e deterministica (sem contexto do pedido, vies fixo), entao o
  mesmo resultado de ferramenta vira o mesmo texto em todo turno e o prefixo
  em cache no provedor nao muda.

Seguranca: escuta so em 127.0.0.1; nunca grava corpo de requisicao nem
cabecalho de autenticacao em log (o Paperclip gravava senha em log, issue
#4759); o cabecalho de autenticacao segue para o provedor sem ser lido.
"""
