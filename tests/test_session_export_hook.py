"""session_export.py: the SessionEnd hook writes to the vault's configured Sessions folder.

The hook hardcoded ``vault / "sessions"``. On this vault — and any vault set up
with Capitalized folder names — that created a second, lowercase ``sessions/``
directory beside the real ``Sessions/``. Indexing, health accounting and search
all iterate ``cfg.vault_folders``, so every transcript written there was
invisible: absent from ChromaDB, unsearchable, uncounted. 29 transcripts spanning
2026-06-10 to 2026-07-30 had accumulated there before it was noticed.

The hook is stdlib-only by design (runs under system python3, no venv), so it
cannot import config.resolve_folder — hence its own resolver, pinned here.

Loaded by path rather than imported: hooks/ is not a package on sys.path.
"""

import importlib.util
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / "src" / "delegation_core" / "hooks" / "session_export.py"


@pytest.fixture(scope="module")
def hook():
    spec = importlib.util.spec_from_file_location("session_export", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CAPS = ["Projects", "Decisions", "Fixes", "Sessions", "Procedures",
        "Reference", "Tools", "Scratch", "Infrastructure"]


def test_resolves_capitalized_sessions_folder(hook, tmp_path):
    resolved = hook._resolve_sessions_dir(tmp_path, {"vault_folders": CAPS})
    assert resolved == tmp_path / "Sessions"


def test_resolves_lowercase_sessions_folder(hook, tmp_path):
    resolved = hook._resolve_sessions_dir(tmp_path, {"vault_folders": ["decisions", "sessions"]})
    assert resolved == tmp_path / "sessions"


def test_resolves_odd_casing_and_whitespace(hook, tmp_path):
    resolved = hook._resolve_sessions_dir(tmp_path, {"vault_folders": ["  SESSIONS  "]})
    assert resolved == tmp_path / "SESSIONS"


def test_defaults_to_capitalized_when_config_has_no_sessions_folder(hook, tmp_path):
    """Capitalized is the shipped wizard default, so an unconfigured vault should
    not be the one that gets a stray lowercase directory."""
    assert hook._resolve_sessions_dir(tmp_path, {"vault_folders": ["Notes"]}) == tmp_path / "Sessions"
    assert hook._resolve_sessions_dir(tmp_path, {}) == tmp_path / "Sessions"


def test_ignores_non_string_entries_in_vault_folders(hook, tmp_path):
    """A hand-edited config.json must not crash the hook on session close."""
    resolved = hook._resolve_sessions_dir(tmp_path, {"vault_folders": [None, 3, "Sessions"]})
    assert resolved == tmp_path / "Sessions"


def test_parses_codex_response_items(hook, tmp_path):
    transcript = tmp_path / "codex-rollout.jsonl"
    transcript.write_text(
        '{"type":"response_item","timestamp":"2026-10-06T12:00:00Z",'
        '"payload":{"type":"message","role":"user",'
        '"content":[{"type":"input_text","text":"Hello"}]}}\n'
        '{"type":"response_item","timestamp":"2026-10-06T12:00:01Z",'
        '"payload":{"item":{"type":"message","role":"assistant",'
        '"content":[{"type":"output_text","text":"Hi"}]}}}\n',
        encoding="utf-8",
    )

    assert hook._parse_transcript(str(transcript)) == [
        {"role": "user", "text": "Hello", "ts": "2026-10-06T12:00:00Z"},
        {"role": "assistant", "text": "Hi", "ts": "2026-10-06T12:00:01Z"},
    ]


def test_reindex_worker_is_hidden_on_windows(hook, monkeypatch):
    monkeypatch.setattr(hook.platform, "system", lambda: "Windows")
    flags = hook._detached_popen_kwargs().get("creationflags", 0)
    assert flags & hook.DETACHED_PROCESS
    assert flags & hook.CREATE_NO_WINDOW
    assert flags & hook.CREATE_NEW_PROCESS_GROUP


def test_transcript_mode_defaults_to_automatic_and_rejects_unknown_values(hook):
    assert hook.transcript_mode({}) == "automatic"
    assert hook.transcript_mode({"session_transcripts": {"mode": "manual"}}) == "manual"
    assert hook.transcript_mode({"session_transcripts": {"mode": "off"}}) == "off"
    assert hook.transcript_mode({"session_transcripts": {"mode": "surprise"}}) == "automatic"


def test_manual_capture_marker_is_single_use(hook, monkeypatch, tmp_path):
    marker = tmp_path / "capture_next_session"
    monkeypatch.setattr(hook, "MANUAL_CAPTURE_FILE", marker)
    marker.with_name("capture_next_session.codex").touch()

    assert hook._manual_capture_requested("codex") is True
    assert not marker.with_name("capture_next_session.codex").exists()
    assert hook._manual_capture_requested("codex") is False


def test_manual_capture_for_one_client_does_not_authorize_the_other(hook, monkeypatch, tmp_path):
    marker = tmp_path / "capture_next_session"
    monkeypatch.setattr(hook, "MANUAL_CAPTURE_FILE", marker)
    marker.with_name("capture_next_session.codex").touch()

    assert hook._manual_capture_requested("claude") is False
    assert hook._manual_capture_requested("codex") is True


def test_capture_permitted_olha_sem_consumir_o_marcador(hook, monkeypatch, tmp_path):
    marker = tmp_path / "capture_next_session"
    monkeypatch.setattr(hook, "MANUAL_CAPTURE_FILE", marker)

    monkeypatch.setattr(hook, "_load_config", lambda: {})
    assert hook.capture_permitted("codex") is True

    monkeypatch.setattr(hook, "_load_config", lambda: {"session_transcripts": {"mode": "off"}})
    assert hook.capture_permitted("codex") is False

    monkeypatch.setattr(hook, "_load_config", lambda: {"session_transcripts": {"mode": "manual"}})
    assert hook.capture_permitted("codex") is False
    marker.with_name("capture_next_session.codex").touch()
    assert hook.capture_permitted("codex") is True
    assert hook.capture_permitted("codex") is True  # ainda la: so quem exporta consome
    assert hook.capture_permitted("claude") is False


def test_o_preambulo_que_o_codex_grava_como_fala_do_usuario_nao_entra(hook, tmp_path):
    """Forma medida em ~/.codex/sessions (codex-cli 0.147.0): o primeiro
    response_item de usuario e o bloco <environment_context>, e a fala real vem depois."""
    import json

    def fala(hora, texto):
        return json.dumps({
            "timestamp": f"2026-08-18T14:43:{hora}Z", "type": "response_item",
            "payload": {"type": "message", "role": "user",
                        "content": [{"type": "input_text", "text": texto}]},
        })

    preambulo = "<environment_context>\n  <cwd>/home/x/proj</cwd>\n  <shell>bash</shell>\n</environment_context>"
    transcript = tmp_path / "rollout.jsonl"
    transcript.write_text(fala("12", preambulo) + "\n" + fala("13", "heartbeat") + "\n", encoding="utf-8")

    # a linha do preambulo tem de ser lida de verdade: sem o filtro ela entraria
    assert json.loads(transcript.read_text(encoding="utf-8").splitlines()[0])

    mensagens = hook._parse_transcript(str(transcript))

    assert [m["text"] for m in mensagens] == ["heartbeat"]
    assert hook._topic(mensagens) == "heartbeat"


def test_a_fala_do_usuario_no_claude_que_comeca_igual_nao_e_descartada(hook, tmp_path):
    """O filtro e do formato do Codex; no Claude Code a mesma abertura e do usuario."""
    transcript = tmp_path / "claude.jsonl"
    transcript.write_text(
        '{"type":"user","timestamp":"2026-10-19T10:00:00Z","message":{"role":"user",'
        '"content":"<environment_context> o que e essa tag?"}}\n',
        encoding="utf-8",
    )

    assert len(hook._parse_transcript(str(transcript))) == 1
