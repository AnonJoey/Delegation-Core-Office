"""A guarda 3 escrevia a mesma linha em toda sessao quando o servidor local nao tem /slots.

Medido num diagnostico de 26/10/2026: 49 tentativas de 06 a 25/10, todas barradas pela
guarda 3 porque o mlx_lm.server responde 404 em /slots. A guarda e certa (sem /slots nao
da para saber se ha trabalho em curso); o log repetido e que era ruido.
"""
from delegation_core.hooks import llama_session_stop as hook


def _usa(tmp_path, monkeypatch, respostas):
    monkeypatch.setattr(hook, "LOG", tmp_path / "llama_stop.log")
    monkeypatch.setattr(hook, "SENTRY", tmp_path / "sem-sentinela")
    monkeypatch.setattr(hook, "load_config", lambda: {"llama_port": 8181})
    monkeypatch.setattr(hook, "http_json", lambda url, timeout=3.0: respostas.get(url.rsplit("/", 1)[-1]))
    parou = []
    monkeypatch.setattr(hook, "stop", lambda pid: parou.append(pid) or "parado")
    return parou


def test_sem_slots_nao_para_e_registra_uma_vez_so(tmp_path, monkeypatch):
    parou = _usa(tmp_path, monkeypatch, {"health": {"status": "ok"}, "slots": None})
    for _ in range(3):
        assert hook.main("{}") == 0
    linhas = (tmp_path / "llama_stop.log").read_text().splitlines()
    assert len(linhas) == 1 and "guarda 3" in linhas[0]
    assert parou == []


def test_mensagem_diferente_entre_as_repeticoes_volta_a_ser_registrada(tmp_path, monkeypatch):
    respostas = {"health": {"status": "ok"}, "slots": None}
    _usa(tmp_path, monkeypatch, respostas)
    hook.main("{}")
    respostas["health"] = None
    hook.main("{}")
    respostas["health"] = {"status": "ok"}
    hook.main("{}")
    assert len((tmp_path / "llama_stop.log").read_text().splitlines()) == 3
