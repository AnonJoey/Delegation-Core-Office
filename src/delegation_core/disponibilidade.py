"""Quais ferramentas funcionam nesta maquina, e por que as outras nao.

Trazido do REA (`docs/mcp-contracts.md`): `tools/list` anuncia so o que da para
chamar agora, e um inventario completo explica cada ferramenta escondida com
motivo e remedio. Aqui, uma ferramenta desligada no config ou sem o extra
instalado ficava na lista do cliente, gastando contexto, e respondia
"disabled" so quando chamada. `search_web`, por exemplo, vem desligada por
padrao (`web_search_enabled=false`) e mesmo assim aparecia para todo agente.

Regra: so se esconde o que CERTAMENTE nao funciona (chave de config falsa,
pacote ausente). Ferramenta que pode falhar por outro motivo continua visivel.
A lista e calculada na subida do daemon; mudar o config pede reinicio, que e
o mesmo que ja valia para essas chaves.
"""

from __future__ import annotations

#: chave do config -> ferramentas que ela liga.
POR_CHAVE = {
    "web_search_enabled": ("search_web",),
    "historico_enabled": ("vault_note_history", "vault_note_diff", "vault_note_restore"),
    "agenda_enabled": ("alerts", "alerts_check", "schedule_list", "schedule_run"),
    "recordacao_enabled": ("recall_stats",),
    "sonho_enabled": ("dream_run", "dream_findings", "dream_dismiss", "dream_apply"),
    "livro_enabled": ("usage_report",),
    "digestao_enabled": ("digest_transcripts",),
    "codigo_enabled": ("vault_note_code", "graph_notes", "graph_changed_notes"),
    "fatos_enabled": ("vault_facts",),
    "referencias_enabled": ("vault_dead_refs",),
    # Desligadas por padrao (porte do ai-memory): sem a chave, a ferramenta nem aparece no tools/list.
    "envelhecimento_enabled": ("vault_forget_sweep", "vault_note_feedback"),
    "passagem_enabled": ("handoff_create", "handoff_pickup", "handoff_list", "handoff_cancel"),
}

#: Chaves que valem `false` quando ausentes do config: o padrao do dataclass nao e `true`.
PADRAO_FALSO = frozenset({"web_search_enabled", "envelhecimento_enabled", "passagem_enabled"})

#: Ferramentas que precisam do extra [graph] (tree-sitter).
EXTRA_GRAFO = ("graph_build", "graph_build_bg", "graph_preview", "graph_hook_install")


def _tem_grafo() -> bool:
    try:
        import tree_sitter  # noqa: F401
        import tree_sitter_python  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def escondidas(cfg, tem_grafo=None) -> dict[str, dict]:
    """{ferramenta: {reason, fix}} para o que nao funciona nesta maquina."""
    saida: dict[str, dict] = {}
    for chave, ferramentas in POR_CHAVE.items():
        padrao = chave not in PADRAO_FALSO
        if not getattr(cfg, chave, padrao):
            for f in ferramentas:
                saida[f] = {"reason": f"disabled in config ({chave}=false)",
                            "fix": f"set {chave} to true in config.json and restart the daemon"}
    if not (_tem_grafo() if tem_grafo is None else tem_grafo):
        for f in EXTRA_GRAFO:
            saida[f] = {"reason": "code-graph extra not installed (tree-sitter missing)",
                        "fix": 'pip install "delegation-core[graph]" and restart the daemon'}
    return saida


def aplicar(mcp, cfg) -> dict[str, dict]:
    ocultas = escondidas(cfg)
    if ocultas:
        mcp.disable(names=set(ocultas))
    return ocultas
