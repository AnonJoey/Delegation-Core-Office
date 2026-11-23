"""`delegation-core approvals` e `delegation-core policy`: o lado humano da governanca."""

from __future__ import annotations

import json


def _aprovacoes():
    from .. import config
    from .aprovacoes import Aprovacoes
    cfg = config.Config.load()
    return Aprovacoes(config.CONFIG_DIR / "approvals.json", validade_h=cfg.approval_ttl_hours)


def cmd_approvals(args) -> int:
    ap = _aprovacoes()
    if args.acao == "list":
        pedidos = ap.listar(args.status)
        if not pedidos:
            print(f"no {args.status} requests")
        for p in pedidos:
            print(f"{p['id']}  {p['status']:8} {p['client']:16} {p['tool']:22} {p['created']}")
            for k, v in p["args_preview"].items():
                print(f"    {k}: {v}")
        return 0
    if args.acao in ("approve", "deny"):
        p = ap.decidir(args.id, aprovar=args.acao == "approve", por="cli", motivo=args.reason or "")
        if p is None:
            print(f"{args.id}: not found (or the prefix matches more than one request)")
            return 1
        print(f"{p['id']}: {p['status']} ({p['client']} -> {p['tool']})")
        if p["status"] == "approved":
            print("The agent can now repeat the same call once, with the same arguments.")
        return 0
    if args.acao == "prune":
        print(f"removed {ap.limpar(args.days)} decided requests older than {args.days} days")
        return 0
    return 1


def cmd_policy(args) -> int:
    from ..config import Config
    from .politica import acao_valida, politica_efetiva, validar_politicas
    cfg = Config.load()
    politicas = dict(cfg.tool_policies or {})
    if args.acao == "show":
        print(json.dumps(politicas, indent=2) if politicas else "no tool_policies (everything allowed)")
        for erro in validar_politicas(politicas):
            print(f"invalid: {erro}")
        return 0
    if args.acao == "check":
        acao, origem = politica_efetiva(politicas, args.client, args.tool)
        print(f"{args.client} -> {args.tool}: {acao} ({origem})")
        return 0
    if args.acao == "set":
        if not acao_valida(args.action):
            print(f"invalid action {args.action!r}: allow, block, require_approval, rate_limit:N/S")
            return 1
        politicas.setdefault(args.client, {})[args.key] = args.action
    elif args.acao == "unset":
        regras = politicas.get(args.client) or {}
        if args.key not in regras:
            print(f"no rule {args.client}/{args.key}")
            return 1
        del regras[args.key]
        if not regras:
            politicas.pop(args.client, None)
    cfg.tool_policies = politicas
    cfg.save()
    print(f"saved. {args.client}: {json.dumps(politicas.get(args.client, {}))}")
    return 0


def registrar(sub) -> dict:
    """Acrescenta os subcomandos ao argparse e devolve {nome: funcao}."""
    p = sub.add_parser("approvals", help="Human approvals requested by tool policies")
    s = p.add_subparsers(dest="acao", required=True)
    pl = s.add_parser("list", help="list approval requests")
    pl.add_argument("--status", default="pending",
                    choices=["pending", "approved", "denied", "used", "expired", "all"], help="which requests to list")
    for nome in ("approve", "deny"):
        pa = s.add_parser(nome, help=f"{nome} a pending request")
        pa.add_argument("id", help="request id")
        pa.add_argument("--reason", default="", help="why, recorded with the decision")
    pp = s.add_parser("prune", help="delete decided requests older than --days")
    pp.add_argument("--days", type=int, default=30, help="age in days")

    p = sub.add_parser("policy", help="Per-client tool policies: allow/block/require_approval/rate_limit")
    s = p.add_subparsers(dest="acao", required=True)
    s.add_parser("show", help="show the configured policies")
    pc = s.add_parser("check", help="which policy applies to a client and a tool")
    pc.add_argument("client", help="client name")
    pc.add_argument("tool", help="tool name")
    ps = s.add_parser("set", help="client ('*' for all), key (a tool or read/write/destructive), action")
    ps.add_argument("client", help="client name, or '*' for all")
    ps.add_argument("key", help="a tool name, or read, write or destructive")
    ps.add_argument("action", help="allow, block, require_approval or rate_limit:N/S")
    pu = s.add_parser("unset", help="remove a policy")
    pu.add_argument("client", help="client name, or '*' for all")
    pu.add_argument("key", help="a tool name, or read, write or destructive")
    return {"approvals": cmd_approvals, "policy": cmd_policy}
