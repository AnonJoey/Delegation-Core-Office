"""Escopo por cliente: token de leitura nao chama ferramenta que escreve.

## Por que existe

O daemon atende Claude Code, Claude Desktop, Codex e, na outra maquina, os
clientes do William, e todos usavam o mesmo token, que pode tudo: escrever e
renomear nota, restaurar versao, reindexar, montar grafo, rodar tarefa. O
openclaw pareia dispositivo e da perfil de acesso por cliente
(`gateway/device-pairing`, `auth-profiles`); o memgraph tem RBAC por papel.
Aqui o minimo util disso: token nomeado, com escopo `read` ou `write`.

## Regras

- **Nega por padrao.** Toda ferramenta esta em LEITURA ou em ESCRITA, e um
  teste falha se aparecer uma ferramenta nova sem classificacao. Ferramenta
  nao classificada exige `write`: e melhor um cliente de leitura levar recusa
  que um cliente de leitura escrever por esquecimento.
- **Na duvida, escrita.** Ferramenta que roda job, muda estado ou tem opcao de
  gravar (`aferir_busca(gravar=True)`, `alerts_check`, `local_task_submit`)
  esta em ESCRITA.
- O token mestre (`server_token`) continua com tudo.
"""

from __future__ import annotations

LEITURA = frozenset({
    "alerts", "approval_list", "ask_vault", "capabilities", "compress", "config_history", "feedback_report", "dream_findings", "graph_affected", "graph_changed_notes", "graph_hook_status", "graph_list",
    "graph_node", "graph_notes", "graph_path", "graph_preview", "graph_query", "graph_report", "graph_stats",
    "heartbeat", "ingest_status", "list_mcp_clients", "local_task_list", "local_task_status", "logs", "memory_get", "memory_list", "memory_query",
    "process_get", "process_list", "process_watchdog", "proxy_stats", "question_list", "recall_output", "read_note", "recall_stats", "schedule_list", "search_vault",
    "search_web", "standup", "task_status", "tool_policy", "usage_report", "vault_find_notes", "vault_find_similar",
    "vault_health_detail", "vault_inbox_status", "vault_dead_refs", "vault_facts", "vault_list_notes", "vault_note_code", "vault_note_diff",
    "vault_note_hash", "vault_note_history", "vault_note_links", "vault_proposals", "vault_stats", "handoff_list",
    "window_list", "workspace_list",
    # Propor nao toca o vault: a proposta so vira mudanca pela CLI, por uma
    # pessoa. E o caminho do Paperclip para agente de baixa confianca.
    "vault_propose_edit",
    # Voto e sinal sobre a busca, so acrescenta num arquivo proprio e nao toca
    # vault nem indice; cliente de leitura e quem mais busca.
    "search_feedback",
    # Ler cartoes grava so a impressao digital DESTE leitor; nao muda o que
    # outro cliente ve nem toca vault ou indice.
    "status_cards",
    # Nucleos (cores/) que so devolvem informacao ou transformam o texto recebido,
    # sem gravar nada.
    "dag_status", "cores_unified_status", "cores_skills_search",
    "cores_sanitize_prompt", "cores_selfhosted_catalog",
})

ESCRITA = frozenset({
    "aferir_busca", "alerts_check", "digest_transcripts", "dream_apply", "dream_dismiss", "dream_run",
    "export_session", "extract_source_maps", "graph_build", "graph_build_bg", "graph_export",
    "graph_hook_install", "graph_hook_uninstall", "ingest_configured", "ingest_configured_bg",
    "ingest_folder", "ingest_folder_bg", "ingest_forget", "local_task_cancel", "local_task_submit", "memory_capture", "memory_forget", "memory_upsert",
    "process_claim", "process_create", "process_update", "question_record", "question_resolve", "question_update", "compress_output", "filter_output", "rea_import_evidence", "relink_folder", "relink_folder_bg", "run_maintenance",
    "run_maintenance_bg", "schedule_run", "status_card_delete", "status_card_save", "vault_note_restore", "vault_reindex_bg", "vault_rename_note",
    "vault_correct_note", "vault_forget_note", "vault_update_note", "window_close", "window_open", "workspace_apply", "workspace_save", "write_note",
    "handoff_create", "handoff_pickup", "handoff_cancel", "vault_forget_sweep", "vault_note_feedback",
    # Nucleos que agem: executam comando de shell (dag_run), leem caminho
    # arbitrario do disco (convert_to_markdown, cores_multimodal_ingest) ou gravam o
    # original para o recall_output (cores_prune_context, como o compress_output).
    # Cliente de leitura nao faz nenhuma dessas.
    "dag_run", "convert_to_markdown", "cores_multimodal_ingest", "cores_prune_context",
})

ESCOPOS_VALIDOS = ("read", "write")


def escopos_de(escopo: str) -> list[str]:
    """`write` inclui `read`."""
    return ["read", "write"] if escopo == "write" else ["read"]


def permitido(ferramenta: str, escopos: list[str] | None) -> bool:
    """None (sem autenticacao, o stdio) ou `master` pode tudo."""
    if escopos is None or "master" in escopos:
        return True
    if ferramenta in LEITURA:
        return "read" in escopos
    return "write" in escopos


def ler_tokens(caminho_config) -> dict:
    """`client_tokens` do config.json, relido so quando o arquivo muda."""
    import json
    from pathlib import Path
    p = Path(caminho_config)
    try:
        m = p.stat().st_mtime_ns
    except OSError:
        return {}
    if _CACHE.get("m") != m:
        try:
            _CACHE["t"] = dict(json.loads(p.read_text(encoding="utf-8")).get("client_tokens") or {})
        except (OSError, ValueError):
            _CACHE["t"] = {}
        _CACHE["m"] = m
    return _CACHE["t"]


_CACHE: dict = {}


from fastmcp.server.middleware import Middleware as _Middleware  # noqa: E402


class EscopoMiddleware(_Middleware):
    """Recusa ferramenta de escrita para token de leitura, com erro tipado.

    Subclasse do Middleware do FastMCP porque e a base que despacha para
    on_call_tool; uma classe solta com o mesmo metodo nunca seria chamada.
    """

    async def on_call_tool(self, context, call_next):
        try:
            from fastmcp.server.dependencies import get_access_token
            tok = get_access_token()
        except Exception:  # noqa: BLE001 - sem contexto de auth (stdio): passa
            tok = None
        escopos = None if tok is None else list(tok.scopes or [])
        nome = getattr(context.message, "name", "")
        if not permitido(nome, escopos):
            from fastmcp.exceptions import ToolError
            raise ToolError(f"permission_denied: the token for {getattr(tok, 'client_id', '?')} "
                            f"is read-only and '{nome}' writes. Ask for a write token "
                            f"(delegation-core token create <name> --write).")
        return await call_next(context)
