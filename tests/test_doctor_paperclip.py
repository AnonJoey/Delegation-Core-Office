from delegation_core import config, doctor_paperclip, portabilidade
from delegation_core.governanca import Aprovacoes


def test_checagens(monkeypatch):
    from delegation_core import registro_clientes
    monkeypatch.setattr(registro_clientes, "estado", lambda cfg: [])
    cfg = config.Config(tool_policies={"*": {"write": "talvez"}})
    st = {c["check"]: c["status"] for c in doctor_paperclip.todas(cfg)}
    assert st == {"state_backup": "warn", "tool_policies": "error", "pending_approvals": "ok",
                  "client_registrations": "ok"}
    config.Config().save()
    portabilidade.backup()
    Aprovacoes(config.CONFIG_DIR / "approvals.json").consumir_ou_pedir("c", "ingest_forget", {})
    st = {c["check"]: c["status"] for c in doctor_paperclip.todas(config.Config())}
    assert st == {"state_backup": "ok", "tool_policies": "ok", "pending_approvals": "warn",
                  "client_registrations": "ok"}
