"""Classe de cada ferramenta e a politica que vale para um cliente.

## Precedencia

Do mais especifico para o mais geral, a primeira que existir vence:

1. `tool_policies[cliente][ferramenta]`
2. `tool_policies[cliente][classe]`
3. `tool_policies["*"][ferramenta]`
4. `tool_policies["*"][classe]`
5. `allow`

A classe e `destructive` quando a ferramenta esta em DESTRUTIVAS, senao `write`
ou `read` conforme `escopos.py`. Ferramenta sem classificacao conta como `write`,
pela mesma regra de nega por padrao dos escopos.
"""

from __future__ import annotations

import re

#: Ferramentas que apagam, sobrescrevem ou desfazem algo que nao volta sozinho.
#: Sempre um subconjunto de escopos.ESCRITA; um teste confere.
DESTRUTIVAS = frozenset({
    # Executa os comandos de shell que vierem no YAML, com a conta do daemon: nada do que um
    # comando apaga volta sozinho. Ficou fora desta lista ate 27/11/2026, classificada como
    # `write`: a politica `destructive: require_approval` nao a alcancava e a dica
    # `destructiveHint` saia falsa para o cliente.
    "dag_run",
    "dream_apply",
    "graph_hook_uninstall",
    "ingest_forget",
    "memory_forget",
    "vault_forget_note",
    "vault_note_restore",
    "vault_rename_note",
    "workspace_apply",
})

CLASSES = ("read", "write", "destructive")
ACOES_VALIDAS = ("allow", "block", "require_approval", "rate_limit:N/S")

_TAXA = re.compile(r"^rate_limit:(\d+)/(\d+)$")


def classe_de(ferramenta: str) -> str:
    from .. import escopos
    if ferramenta in DESTRUTIVAS:
        return "destructive"
    if ferramenta in escopos.LEITURA:
        return "read"
    return "write"


def ler_taxa(acao: str) -> tuple[int, int] | None:
    """`rate_limit:10/60` vira (10, 60). Qualquer outra coisa, None."""
    m = _TAXA.match(acao or "")
    if not m:
        return None
    n, s = int(m.group(1)), int(m.group(2))
    return (n, s) if n > 0 and s > 0 else None


def acao_valida(acao: str) -> bool:
    return acao in ("allow", "block", "require_approval") or ler_taxa(acao) is not None


def politica_efetiva(politicas: dict | None, cliente: str, ferramenta: str) -> tuple[str, str]:
    """(acao, de onde veio). A origem vai na mensagem de recusa, para a pessoa achar a regra."""
    politicas = politicas or {}
    classe = classe_de(ferramenta)
    for chave_cliente in (cliente, "*"):
        regras = politicas.get(chave_cliente)
        if not isinstance(regras, dict):
            continue
        for chave in (ferramenta, classe):
            acao = regras.get(chave)
            if isinstance(acao, str) and acao_valida(acao):
                return acao, f"tool_policies[{chave_cliente!r}][{chave!r}]"
    return "allow", "default"


def validar_politicas(politicas) -> list[str]:
    """Erros legiveis de um `tool_policies` escrito a mao. Lista vazia se esta certo."""
    erros = []
    if politicas in (None, {}):
        return erros
    if not isinstance(politicas, dict):
        return [f"tool_policies must be an object, got {type(politicas).__name__}"]
    for cliente, regras in politicas.items():
        if not isinstance(regras, dict):
            erros.append(f"tool_policies[{cliente!r}] must be an object")
            continue
        for chave, acao in regras.items():
            if not isinstance(acao, str) or not acao_valida(acao):
                erros.append(f"tool_policies[{cliente!r}][{chave!r}] = {acao!r}: "
                             f"use one of {', '.join(ACOES_VALIDAS)}")
    return erros
