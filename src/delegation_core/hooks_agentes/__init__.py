"""Hooks de agente em Python: reescrevem comandos de shell para passar pelos filtros.

Porte dos hooks do RTK (`hooks/` e `src/hooks/hook_cmd.rs`, Apache 2.0). La,
cada agente tinha um script bash ou um plugin TypeScript que chamava o binario
`rtk rewrite`; aqui a decisao mora em `decidir()` e cada host tem um adaptador
que le o payload dele e responde no formato que ele espera.

A regra que muda em relacao ao RTK: **o hook nunca concede permissao.** O RTK
devolvia `allow` quando uma regra do proprio usuario ja permitiria; aqui a
resposta ou omite a decisao (o host segue o fluxo dele) ou pede confirmacao
(`ask`, `ask_user`), e so reescreve comando simples (sem pipe, `&&`, `;`,
redirecionamento ou subshell).

Hosts: claude (Claude Code), codex, cursor, vscode e copilot-cli e copilot-ide
(GitHub Copilot), gemini, antigravity, vibe, trae, droid e hermes (plugin
Python). OpenCode e Pi so carregam plugin TypeScript: `scripts/opencode.ts` e
`scripts/pi.ts` sao calcos de poucas linhas que chamam `delegation-core rewrite`.
"""

from .nucleo import HOSTS, decidir, responder

__all__ = ["HOSTS", "decidir", "responder"]
