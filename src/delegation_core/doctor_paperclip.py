"""Checagens do doctor para as funcionalidades trazidas do Paperclip.

Modulo proprio pela mesma razao do `doctor_enriquecimento`: some sem tocar nas
checagens de base, e uma checagem quebrada aqui nao derruba o doctor.
"""

from __future__ import annotations


def check_backup() -> dict:
    from .portabilidade import estado_backups
    st = estado_backups()
    if not st["count"]:
        return {"check": "state_backup", "status": "warn",
                "detail": "no local backup of config and state yet",
                "fix": "delegation-core backup"}
    if st["age_days"] > 7:
        return {"check": "state_backup", "status": "warn",
                "detail": f"newest backup is {st['age_days']} days old ({st['newest']})",
                "fix": "delegation-core backup"}
    return {"check": "state_backup", "status": "ok",
            "detail": f"{st['count']} backups, newest {st['age_days']} days old"}


def check_politicas(cfg) -> dict:
    from .governanca import validar_politicas
    erros = validar_politicas(getattr(cfg, "tool_policies", {}))
    if erros:
        return {"check": "tool_policies", "status": "error", "detail": "; ".join(erros),
                "fix": "delegation-core policy show / policy unset"}
    n = sum(len(v) for v in (cfg.tool_policies or {}).values() if isinstance(v, dict))
    return {"check": "tool_policies", "status": "ok",
            "detail": f"{n} rules" if n else "none (every tool allowed by scope alone)"}


def check_aprovacoes_pendentes() -> dict:
    from . import config
    from .governanca import Aprovacoes
    pend = Aprovacoes(config.CONFIG_DIR / "approvals.json").listar("pending")
    if pend:
        return {"check": "pending_approvals", "status": "warn",
                "detail": f"{len(pend)} tool calls waiting for a human: "
                          + ", ".join(f"{p['id']} ({p['tool']})" for p in pend[:5]),
                "fix": "delegation-core approvals list"}
    return {"check": "pending_approvals", "status": "ok", "detail": "none"}


def todas(cfg) -> list[dict]:
    saida = []
    from .registro_clientes import check as check_clientes
    for f in (check_backup, lambda: check_politicas(cfg), check_aprovacoes_pendentes, lambda: check_clientes(cfg)):
        try:
            saida.append(f())
        except Exception as e:  # noqa: BLE001
            saida.append({"check": "paperclip_checks", "status": "warn", "detail": f"could not run: {e}"})
    return saida
