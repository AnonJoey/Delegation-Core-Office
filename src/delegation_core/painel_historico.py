"""O historico de uma nota no painel: versoes, diff e restaurar.

Camada fina sobre `historico_vault`, para as rotas /api/vault/note/history,
/diff e /restore. A edicao pelo painel tambem passa a guardar a versao que
esta sendo sobrescrita (`antes_de_salvar`), porque o historico so fotografava
passes em lote e a varredura horaria: uma edicao ruim feita no painel ficava
sem volta ate a proxima hora cheia.
"""

from __future__ import annotations

from . import historico_vault


def historia(cfg, rel: str, limite: int = 50) -> dict:
    h = historico_vault.abrir(cfg)
    if h is None:
        return {"error": "note history is disabled (historico_enabled=false)"}
    return {"path": rel, "versions": h.versoes(rel, limite=limite)}


def diff(cfg, rel: str, de: int = 2, para: int = 1) -> dict:
    h = historico_vault.abrir(cfg)
    if h is None:
        return {"error": "note history is disabled (historico_enabled=false)"}
    d = h.diff(rel, de=de, para=para)
    if not d["ok"]:
        return {"error": f"version {de} or {para} of {rel} not found", "versions": d["versoes"]}
    return d


def antes_de_salvar(cfg, rel: str) -> None:
    """Guarda o texto atual de `rel` antes de o painel sobrescrever. Nunca levanta."""
    try:
        h = historico_vault.abrir(cfg)
        if h is None:
            return
        from pathlib import Path
        p = Path(cfg.vault) / rel
        if p.is_file():
            h.registrar(rel, p.read_bytes(), origem="antes de editar no painel")
    except Exception:  # noqa: BLE001 - guardar e protecao; nao impede salvar
        pass


def depois_de_salvar(cfg, rel: str, texto: str) -> None:
    try:
        h = historico_vault.abrir(cfg)
        if h is not None:
            h.registrar(rel, texto, origem="editada no painel")
    except Exception:  # noqa: BLE001
        pass
