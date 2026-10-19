"""Hooks de sessao como parte do pacote: um comando, um processo por evento.

Ate a v0.14.0 eram tres scripts copiados para ~/.delegation_core/hooks/ e
registrados a mao. Em 03/10/2026 a copia do session_export.py estava atras da
arvore, e so o doctor percebeu. O fim de sessao abria dois processos. Agora o
registro aponta para `delegation-core-hook` e o instalador e quem o escreve.
"""

from __future__ import annotations

import io
import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from delegation_core import clients
from delegation_core.hooks import entrada


@pytest.fixture(autouse=True)
def politica_automatica(monkeypatch):
    """O hook do Codex consulta a politica antes de copiar o transcript. Sem isto
    os testes leriam o config.json de quem os roda."""
    from delegation_core.hooks import session_export
    monkeypatch.setattr(session_export, "_load_config", lambda: {})


# ── o comando ────────────────────────────────────────────────────────────────


def test_fim_de_sessao_roda_os_dois_passos_com_a_mesma_entrada(monkeypatch):
    from delegation_core.hooks import llama_session_stop, session_export

    vistos = []
    monkeypatch.setattr(session_export, "main", lambda raw: vistos.append(("export", raw)))
    monkeypatch.setattr(llama_session_stop, "main", lambda raw: vistos.append(("stop", raw)))
    monkeypatch.setattr("sys.stdin", io.StringIO('{"session_id": "abc"}'))
    assert entrada.main(["session-end"]) == 0
    assert vistos == [("export", '{"session_id": "abc"}'), ("stop", '{"session_id": "abc"}')]


def test_um_passo_que_falha_nao_impede_o_outro(monkeypatch, capsys):
    from delegation_core.hooks import llama_session_stop, session_export

    parou = []

    def explode(raw):
        raise RuntimeError("disco cheio")

    monkeypatch.setattr(session_export, "main", explode)
    monkeypatch.setattr(llama_session_stop, "main", lambda raw: parou.append(raw))
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    assert entrada.main(["session-end"]) == 0
    assert parou == ["{}"]
    assert "session_export falhou" in capsys.readouterr().err


def test_o_export_nao_encerra_o_processo(monkeypatch):
    """session_export.main usava sys.exit(0); no processo unico isso mataria
    o passo seguinte."""
    from delegation_core.hooks import session_export

    assert session_export.main("") == 0
    assert session_export.main("nao e json") == 0


def test_evento_desconhecido_e_erro_de_uso():
    assert entrada.main(["session-middle"]) == 2


def test_codex_session_start_emite_protocolo_e_reutiliza_o_brief(monkeypatch, capsys):
    from delegation_core.hooks import session_start_brief

    chamadas = []
    monkeypatch.setattr(session_start_brief, "main", lambda: chamadas.append(True))

    assert entrada.main(["codex-session-start"]) == 0
    assert chamadas == [True]
    assert "Delegation Core is available" in capsys.readouterr().out


def test_codex_session_end_only_dispatches_a_detached_worker(monkeypatch, tmp_path):
    import delegation_core.config as config
    calls = []
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(entrada, "_detached_popen_kwargs", lambda: {})
    monkeypatch.setattr(
        entrada.subprocess,
        "Popen",
        lambda args, **kwargs: (calls.append((args, kwargs)) or SimpleNamespace(pid=1234)),
    )
    monkeypatch.setattr("sys.stdin", io.StringIO('{"session_id":"codex-1","transcript_path":"C:/Example/t.jsonl"}'))

    assert entrada.main(["codex-session-end"]) == 0
    assert len(calls) == 1
    assert calls[0][0][-2] == "session-end-file"
    assert Path(calls[0][0][-1]).is_file()


def test_codex_worker_is_hidden_on_windows(monkeypatch):
    monkeypatch.setattr(entrada, "_is_windows", lambda: True)
    flags = entrada._detached_popen_kwargs().get("creationflags", 0)
    assert flags & entrada.DETACHED_PROCESS
    assert flags & entrada.CREATE_NO_WINDOW
    assert flags & entrada.CREATE_NEW_PROCESS_GROUP


def test_codex_session_end_copies_transcript_before_dispatch(monkeypatch, tmp_path):
    import delegation_core.config as config

    transcript = tmp_path / "rollout.jsonl"
    transcript.write_text('{"type":"user"}\n', encoding="utf-8")
    calls = []
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "runtime")
    monkeypatch.setattr(entrada, "_detached_popen_kwargs", lambda: {})
    monkeypatch.setattr(
        entrada.subprocess,
        "Popen",
        lambda args, **kwargs: (calls.append((args, kwargs)) or SimpleNamespace(pid=1234)),
    )

    entrada.codex_session_end(json.dumps({"session_id": "codex-1", "transcript_path": str(transcript)}))

    payload = json.loads(Path(calls[0][0][-1]).read_text(encoding="utf-8"))
    snapshot = Path(payload["transcript_path"])
    assert snapshot != transcript
    assert snapshot.read_text(encoding="utf-8") == transcript.read_text(encoding="utf-8")
    assert payload["_delegation_core_snapshot_path"] == str(snapshot)


def test_codex_worker_removes_transcript_snapshot(monkeypatch, tmp_path):
    import delegation_core.config as config
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    pasta = tmp_path / "session_hook_payloads"
    pasta.mkdir()
    snapshot = pasta / "snapshot.jsonl"
    snapshot.write_text('{"type":"user"}\n', encoding="utf-8")
    payload = pasta / "payload.json"
    payload.write_text(json.dumps({
        "session_id": "codex-1",
        "transcript_path": str(snapshot),
        "_delegation_core_snapshot_path": str(snapshot),
    }), encoding="utf-8")
    monkeypatch.setattr(entrada, "session_end", lambda raw, client: None)

    entrada.session_end_file(str(payload))

    assert not snapshot.exists()

def test_register_codex_hook_preserves_other_handlers(tmp_path):
    hooks = tmp_path / "hooks.json"
    hooks.write_text(json.dumps({"hooks": {"SessionEnd": [{"hooks": [
        {"type": "command", "command": "other-tool"}]}]}}), encoding="utf-8")

    result = clients.register_codex_session_hook(hooks_path=hooks)

    saved = json.loads(hooks.read_text(encoding="utf-8"))
    commands = [h["command"] for group in saved["hooks"]["SessionEnd"] for h in group["hooks"]]
    start_commands = [h["command"] for group in saved["hooks"]["SessionStart"] for h in group["hooks"]]
    assert result["status"] == "installed"
    assert "other-tool" in commands
    start_command = f'{sys.executable} -X utf8 -m delegation_core.hooks.entrada codex-session-start'
    end_command = f'{sys.executable} -X utf8 -m delegation_core.hooks.entrada codex-session-end'
    assert start_command in start_commands
    assert end_command in commands
    start_hook = next(h for group in saved["hooks"]["SessionStart"] for h in group["hooks"]
                      if h["command"] == start_command)
    end_hook = next(h for group in saved["hooks"]["SessionEnd"] for h in group["hooks"]
                    if h["command"] == end_command)
    assert start_hook["timeout"] == 30
    assert "commandWindows" not in start_hook
    assert "commandWindows" not in end_hook


def test_register_codex_hook_replaces_legacy_generic_handlers(tmp_path):
    hooks = tmp_path / "hooks.json"
    hooks.write_text(json.dumps({"hooks": {
        "SessionStart": [{"hooks": [
            {"type": "command", "command": "other-start"},
            {"type": "command", "command": "delegation-core-hook session-start"},
        ]}],
        "SessionEnd": [{"hooks": [
            {"type": "command", "command": "other-end"},
            {"type": "command", "command": "python -m delegation_core.hooks.entrada session-end"},
        ]}],
    }}), encoding="utf-8")

    result = clients.register_codex_session_hook(hooks_path=hooks)

    assert result["status"] == "updated"
    assert result["replaced"] == 2
    assert _comandos(hooks, "SessionStart") == [
        "other-start",
        f'{sys.executable} -X utf8 -m delegation_core.hooks.entrada codex-session-start',
    ]
    assert _comandos(hooks, "SessionEnd") == [
        "other-end",
        f'{sys.executable} -X utf8 -m delegation_core.hooks.entrada codex-session-end',
    ]


def test_remove_os_dois_hooks_do_codex_sem_afetar_outros(tmp_path):
    hooks = tmp_path / "hooks.json"
    hooks.write_text(json.dumps({"hooks": {
        "SessionStart": [{"hooks": [{"type": "command", "command": "other-start"},
                                      {"type": "command", "command": "python -m delegation_core.hooks.entrada codex-session-start"}]}],
        "SessionEnd": [{"hooks": [{"type": "command", "command": "delegation-core-hook codex-session-end"}]}],
    }}), encoding="utf-8")

    result = clients.unregister_codex_session_hook(hooks_path=hooks)

    saved = json.loads(hooks.read_text(encoding="utf-8"))
    assert result["status"] == "removed"
    assert result["removed"] == 2
    assert _comandos(hooks, "SessionStart") == ["other-start"]
    assert "SessionEnd" not in saved["hooks"]


def test_trust_review_so_e_pedido_quando_algo_foi_escrito(tmp_path):
    hooks = tmp_path / "hooks.json"

    primeira = clients.register_codex_session_hook(hooks_path=hooks)
    segunda = clients.register_codex_session_hook(hooks_path=hooks)

    assert primeira["status"] == "installed" and primeira["trust_review_required"] is True
    assert segunda["status"] == "already-configured" and segunda["trust_review_required"] is False


def test_os_hooks_do_codex_ja_estao_no_lugar_quando_o_codex_chega_depois(tmp_path):
    """Registrar nao depende de o Codex estar instalado na hora do setup: o
    arquivo fica esperando em ~/.codex/ e o Codex o le quando existir. Se alguem
    condicionar o registro a ~/.codex, quem instala o Codex depois fica sem
    hook e sem aviso (o post-install roda antes do wizard, e um update so
    repetiria o mesmo teste)."""
    hooks = tmp_path / "casa-sem-codex" / ".codex" / "hooks.json"
    assert not hooks.parent.exists()

    resultado = clients.register_codex_session_hook(hooks_path=hooks)

    assert resultado["status"] == "installed"
    salvo = json.loads(hooks.read_text(encoding="utf-8"))
    assert set(salvo["hooks"]) == {"SessionStart", "SessionEnd"}
    assert _comandos(hooks, "SessionStart") == [
        f"{sys.executable} -X utf8 -m delegation_core.hooks.entrada codex-session-start"]


# ── a politica vale antes de o hook do Codex copiar o transcript ─────────────


@pytest.fixture
def despacho(monkeypatch, tmp_path):
    """Roda `codex_session_end` sem iniciar processo nenhum e devolve o que ele fez."""
    import delegation_core.config as config
    from delegation_core.hooks import session_export

    transcript = tmp_path / "rollout.jsonl"
    transcript.write_text('{"type":"user","message":{"content":"senha hunter2"}}\n', encoding="utf-8")
    marcador = tmp_path / "capture_next_session"
    chamadas: list = []
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "runtime")
    monkeypatch.setattr(session_export, "MANUAL_CAPTURE_FILE", marcador)
    monkeypatch.setattr(entrada, "_detached_popen_kwargs", lambda: {})
    monkeypatch.setattr(entrada.subprocess, "Popen",
                        lambda args, **kw: (chamadas.append(args) or SimpleNamespace(pid=1)))

    def rodar(modo=None):
        monkeypatch.setattr(session_export, "_load_config",
                            lambda: {"session_transcripts": {"mode": modo}} if modo else {})
        chamadas.clear()
        entrada.codex_session_end(json.dumps({"session_id": "c1", "transcript_path": str(transcript)}))
        pasta = tmp_path / "runtime" / "session_hook_payloads"
        arquivos = sorted(pasta.glob("*")) if pasta.exists() else []
        payload = json.loads(Path(chamadas[0][-1]).read_text(encoding="utf-8")) if chamadas else None
        return SimpleNamespace(chamadas=list(chamadas), arquivos=arquivos, payload=payload,
                               marcador=marcador, pasta=pasta)

    return rodar


def test_modo_off_nao_copia_o_transcript_mas_o_worker_ainda_roda(despacho):
    r = despacho("off")

    assert [p for p in r.arquivos if p.suffix == ".jsonl"] == []
    assert len(r.chamadas) == 1
    assert "transcript_path" not in r.payload and r.payload["session_id"] == "c1"


def test_modo_manual_sem_pedido_nao_copia_o_transcript(despacho):
    r = despacho("manual")

    assert [p for p in r.arquivos if p.suffix == ".jsonl"] == []
    assert "transcript_path" not in r.payload


def test_modo_manual_com_pedido_copia_e_nao_consome_o_marcador(despacho):
    from delegation_core.hooks import session_export
    session_export.MANUAL_CAPTURE_FILE.with_name("capture_next_session.codex").touch()

    r = despacho("manual")

    assert [p for p in r.arquivos if p.suffix == ".jsonl"] != []
    assert "transcript_path" in r.payload
    # quem consome e o worker, ao exportar; o despachante so olha
    assert r.marcador.with_name("capture_next_session.codex").exists()


def test_modo_manual_com_pedido_de_outro_cliente_nao_copia(despacho):
    from delegation_core.hooks import session_export
    session_export.MANUAL_CAPTURE_FILE.with_name("capture_next_session.claude").touch()

    r = despacho("manual")

    assert [p for p in r.arquivos if p.suffix == ".jsonl"] == []


def test_modo_automatico_copia(despacho):
    r = despacho(None)

    assert len([p for p in r.arquivos if p.suffix == ".jsonl"]) == 1


def test_falha_ao_iniciar_o_worker_nao_deixa_o_transcript_cru_para_tras(despacho, monkeypatch):
    def falha(args, **kw):
        raise OSError("sem processo")
    monkeypatch.setattr(entrada.subprocess, "Popen", falha)

    r = despacho(None)

    assert r.arquivos == []


def test_o_que_um_worker_morto_deixou_ha_mais_de_um_dia_e_varrido(despacho):
    r = despacho(None)
    pasta = r.pasta
    velho = pasta / "codex-transcript-velho.jsonl"
    velho.write_text("cru", encoding="utf-8")
    recente = pasta / "codex-transcript-recente.jsonl"
    recente.write_text("cru", encoding="utf-8")
    alheio = pasta / "outra-coisa.txt"
    alheio.write_text("nao e nosso", encoding="utf-8")
    dois_dias = time.time() - 2 * 24 * 3600
    for arquivo in (velho, alheio):
        os.utime(arquivo, (dois_dias, dois_dias))

    despacho(None)

    assert not velho.exists()
    assert recente.exists()
    assert alheio.exists()


def test_o_worker_nao_apaga_o_que_esta_fora_da_pasta_de_payloads(monkeypatch, tmp_path):
    import delegation_core.config as config
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "runtime")
    (tmp_path / "runtime" / "session_hook_payloads").mkdir(parents=True)
    visto = []
    monkeypatch.setattr(entrada, "session_end", lambda raw, client: visto.append(raw))

    importante = tmp_path / "importante.txt"
    importante.write_text("nao apague", encoding="utf-8")
    # um payload fora da pasta e recusado e nao e lido nem apagado
    fora = tmp_path / "fora.json"
    fora.write_text(json.dumps({"session_id": "x"}), encoding="utf-8")
    entrada.session_end_file(str(fora))
    assert fora.exists() and visto == []

    # um payload legitimo que aponta para um arquivo de fora nao o apaga
    dentro = tmp_path / "runtime" / "session_hook_payloads" / "codex-1.json"
    dentro.write_text(json.dumps({"session_id": "x", "_delegation_core_snapshot_path": str(importante)}),
                      encoding="utf-8")
    entrada.session_end_file(str(dentro))
    assert len(visto) == 1
    assert not dentro.exists()
    assert importante.exists()


def test_o_comando_esta_declarado_no_pyproject():
    texto = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    assert 'delegation-core-hook = "delegation_core.hooks.entrada:main"' in texto


def test_nao_ha_mais_pasta_hooks_solta_no_repositorio():
    assert not (Path(__file__).resolve().parents[1] / "hooks").exists()


# ── o registro ───────────────────────────────────────────────────────────────


def test_a_suite_nao_enxerga_o_settings_real():
    assert clients.CLAUDE_SETTINGS != Path.home() / ".claude" / "settings.json"


def test_a_suite_nao_enxerga_o_hooks_json_real_do_codex():
    assert clients.CODEX_HOOKS != Path.home() / ".codex" / "hooks.json"


def _settings(tmp_path, dados) -> Path:
    p = tmp_path / "settings.json"
    p.write_text(json.dumps(dados), encoding="utf-8")
    return p


def _comandos(path: Path, evento: str) -> list[str]:
    dados = json.loads(path.read_text(encoding="utf-8"))
    return [h["command"] for g in dados["hooks"].get(evento, []) for h in g["hooks"]]


def test_registro_troca_os_scripts_copiados_e_preserva_os_de_terceiros(tmp_path):
    p = _settings(tmp_path, {"hooks": {
        "SessionStart": [{"matcher": "*", "hooks": [
            {"type": "command", "command": "python3 /home/u/.delegation_core/hooks/session_start_brief.py"},
            {"type": "command", "command": "outro-programa --x"}]}],
        "SessionEnd": [{"matcher": "*", "hooks": [
            {"type": "command", "command": "python3 /home/u/.delegation_core/hooks/session_export.py"}]},
            {"matcher": "*", "hooks": [
            {"type": "command", "command": "python3 /home/u/.delegation_core/hooks/llama_session_stop.py"}]}],
    }, "model": "x"})
    exe = tmp_path / "bin" / "delegation-core-hook"
    r = clients.register_session_hooks(settings_path=p, executable=exe)
    assert r["status"] == "updated" and r["replaced"] == 3
    assert _comandos(p, "SessionStart") == ["outro-programa --x", f'"{exe}" session-start']
    assert _comandos(p, "SessionEnd") == [f'"{exe}" session-end']
    assert json.loads(p.read_text())["model"] == "x"
    assert (tmp_path / "settings.json.dc-backup").exists()


def test_registro_e_idempotente(tmp_path):
    p = _settings(tmp_path, {})
    exe = tmp_path / "delegation-core-hook"
    assert clients.register_session_hooks(settings_path=p, executable=exe)["status"] == "installed"
    assert clients.register_session_hooks(settings_path=p, executable=exe)["status"] == "already-configured"
    assert len(_comandos(p, "SessionEnd")) == 1


def test_json_invalido_nao_e_tocado(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{ quebrado", encoding="utf-8")
    assert clients.register_session_hooks(settings_path=p)["status"] == "error"
    assert p.read_text() == "{ quebrado"


def test_registro_apaga_as_copias_antigas(tmp_path):
    from delegation_core import config
    pasta = Path(config.CONFIG_DIR) / "hooks"
    pasta.mkdir(parents=True, exist_ok=True)
    for nome in clients.LEGACY_HOOK_SCRIPTS:
        (pasta / nome).write_text("# copia antiga")
    r = clients.register_session_hooks(settings_path=_settings(tmp_path, {}),
                                       executable=tmp_path / "x")
    assert sorted(r["legacy_copies_removed"]) == sorted(clients.LEGACY_HOOK_SCRIPTS)
    assert not pasta.exists()


def test_desregistro_tira_so_os_nossos(tmp_path):
    p = _settings(tmp_path, {"hooks": {"SessionEnd": [{"matcher": "*", "hooks": [
        {"type": "command", "command": '"/v/bin/delegation-core-hook" session-end'},
        {"type": "command", "command": "outro"}]}]}})
    r = clients.unregister_session_hooks(settings_path=p)
    assert r["status"] == "removed" and r["removed"] == 1
    assert _comandos(p, "SessionEnd") == ["outro"]


# ── o doctor ─────────────────────────────────────────────────────────────────


def test_doctor_ok_com_o_registro_novo(tmp_path):
    from delegation_core import doctor
    exe = tmp_path / "delegation-core-hook"
    exe.write_text("")
    p = _settings(tmp_path, {})
    clients.register_session_hooks(settings_path=p, executable=exe)
    assert doctor.check_hooks(p)["status"] == "ok"


def test_doctor_avisa_registro_antigo_e_executavel_sumido(tmp_path):
    from delegation_core import doctor
    antigo = _settings(tmp_path, {"hooks": {"SessionEnd": [{"hooks": [
        {"type": "command", "command": "python3 /h/.delegation_core/hooks/session_export.py"}]}]}})
    r = doctor.check_hooks(antigo)
    assert r["status"] == "warn" and "session_export.py" in r["detail"]
    sumido = tmp_path / "s2.json"
    sumido.write_text("{}")
    clients.register_session_hooks(settings_path=sumido,
                                   executable=tmp_path / "venv-apagado" / "delegation-core-hook")
    r = doctor.check_hooks(sumido)
    assert r["status"] == "warn" and "executable missing" in r["detail"]


def test_doctor_avisa_quando_nada_esta_registrado(tmp_path):
    from delegation_core import doctor
    r = doctor.check_hooks(_settings(tmp_path, {}))
    assert r["status"] == "warn" and "not registered" in r["detail"]
