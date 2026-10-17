"""`delegation-core-hook`: um processo por evento de sessao do Claude Code.

    delegation-core-hook session-start   resumo do que mudou no vault
    delegation-core-hook session-end     exporta a transcricao e para o
                                         modelo local ocioso

O fim de sessao le a entrada do hook uma vez e entrega aos dois passos, em
sequencia, no mesmo processo. Antes eram dois hooks registrados e dois
interpretadores. Um passo que falha nao impede o outro, e nada aqui devolve
erro ao Claude Code: o encerramento da sessao nunca pode quebrar por causa de
um hook.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

USO = "uso: delegation-core-hook {session-start|session-end|codex-session-start|codex-session-end}"


def _passo(nome: str, fazer: Callable[[], object]) -> None:
    try:
        fazer()
    except Exception as e:  # um passo nunca derruba o outro nem a sessao
        sys.stderr.write(f"delegation-core-hook: {nome} falhou: {type(e).__name__}: {e}\n")


def session_start() -> None:
    from . import session_start_brief
    _passo("session_start_brief", session_start_brief.main)


def codex_session_start() -> None:
    """Provide the Delegation Core protocol plus the usual session brief."""
    print(
        "Delegation Core is available in this session. Use its MCP tools for "
        "project context; call heartbeat for lengthy work and export_session "
        "before handoff when a durable project record is useful."
    )
    session_start()


def session_end(raw: str, client: str = "claude") -> None:
    from . import llama_session_stop, session_export
    if client == "claude":
        # Keep the established one-argument hook contract for Claude Code and
        # for third-party wrappers that import this function directly.
        _passo("session_export", lambda: session_export.main(raw))
    else:
        _passo("session_export", lambda: session_export.main(raw, client=client))
    _passo("llama_session_stop", lambda: llama_session_stop.main(raw))


def _detached_popen_kwargs() -> dict:
    if os.name == "nt":
        # Do not create a visible console for the short-lived export worker.
        # A normal child outlives its parent on Windows; CREATE_NO_WINDOW keeps
        # that child headless while its own process group isolates Ctrl+C.
        return {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def codex_session_end(raw: str) -> None:
    """Return from Codex's three-second SessionEnd hook before export work starts.

    Codex gives hooks a transcript path but limits SessionEnd command handlers to
    three seconds. Persisting the small hook payload and handing it to a detached
    worker keeps closing the client responsive while preserving the documented
    payload for the existing redaction and indexing flow.
    """
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return
        transcript = data.get("transcript_path")
        has_transcript = isinstance(transcript, str) and bool(transcript)
        from ..config import CONFIG_DIR
        payload_dir = CONFIG_DIR / "session_hook_payloads"
        payload_dir.mkdir(parents=True, exist_ok=True)
        # Codex can move the rollout file as soon as SessionEnd returns. Copy
        # it while the hook still owns a live path; the detached worker then
        # reads this private snapshot instead of racing the archive operation.
        if has_transcript and Path(transcript).is_file():
            with tempfile.NamedTemporaryFile("wb", suffix=".jsonl", prefix="codex-transcript-",
                                             dir=payload_dir, delete=False) as snapshot_file:
                snapshot = Path(snapshot_file.name)
                with Path(transcript).open("rb") as source_file:
                    shutil.copyfileobj(source_file, snapshot_file)
            data = dict(data)
            data["transcript_path"] = str(snapshot)
            data["_delegation_core_snapshot_path"] = str(snapshot)
        with tempfile.NamedTemporaryFile("w", suffix=".json", prefix="codex-",
                                         dir=payload_dir, delete=False, encoding="utf-8") as fh:
            json.dump(data, fh)
            payload = Path(fh.name)
        subprocess.Popen(
            [sys.executable, "-m", "delegation_core.hooks.entrada", "session-end-file", str(payload)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            **_detached_popen_kwargs(),
        )
    except Exception as e:
        sys.stderr.write(f"delegation-core-hook: codex session dispatch failed: {type(e).__name__}: {e}\n")


def session_end_file(payload: str) -> None:
    path = Path(payload)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        sys.stderr.write(f"delegation-core-hook: cannot read session payload: {e}\n")
        return
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return
    snapshot_path = data.get("_delegation_core_snapshot_path") if isinstance(data, dict) else None
    try:
        session_end(raw, client="codex")
    finally:
        if isinstance(snapshot_path, str):
            try:
                Path(snapshot_path).unlink(missing_ok=True)
            except OSError:
                pass


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    evento = args[0] if args else ""
    if evento == "session-start":
        session_start()
        return 0
    if evento == "session-end":
        try:
            raw = sys.stdin.read()
        except Exception:
            raw = ""
        session_end(raw)
        return 0
    if evento == "codex-session-start":
        codex_session_start()
        return 0
    if evento == "codex-session-end":
        try:
            raw = sys.stdin.read()
        except Exception:
            raw = ""
        codex_session_end(raw)
        return 0
    if evento == "session-end-file" and len(args) == 2:
        session_end_file(args[1])
        return 0
    sys.stderr.write(USO + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
