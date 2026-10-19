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
import time
from pathlib import Path
from typing import Callable

USO = "uso: delegation-core-hook {session-start|session-end|codex-session-start|codex-session-end}"

# The constants are only exposed by subprocess on Windows. Keep their documented
# values here so the stdlib-only hook can be imported and unit-tested on POSIX
# while still creating the intended Windows process flags at runtime.
DETACHED_PROCESS = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


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


def _is_windows() -> bool:
    return os.name == "nt"


def _detached_popen_kwargs() -> dict:
    if _is_windows():
        # Do not create a visible console for the short-lived export worker.
        # A normal child outlives its parent on Windows; CREATE_NO_WINDOW keeps
        # that child headless while its own process group isolates Ctrl+C.
        return {"creationflags": DETACHED_PROCESS | CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def codex_session_end(raw: str) -> None:
    """Return from Codex's three-second SessionEnd hook before export work starts.

    Codex gives hooks a transcript path but limits SessionEnd command handlers to
    three seconds. Persisting the small hook payload and handing it to a detached
    worker keeps closing the client responsive while preserving the documented
    payload for the existing redaction and indexing flow.
    """
    created: list[Path] = []
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return
        from . import session_export
        payload_dir = _payload_dir()
        payload_dir.mkdir(parents=True, exist_ok=True)
        _sweep_stale_payloads(payload_dir)
        transcript = data.get("transcript_path")
        if not session_export.capture_permitted("codex"):
            # The policy says no raw transcript, so nothing may copy one. The
            # worker still runs for the local-model shutdown, but it is never
            # handed a path to read.
            data = {key: value for key, value in data.items() if key != "transcript_path"}
        elif isinstance(transcript, str) and transcript and Path(transcript).is_file():
            # Codex can move the rollout file as soon as SessionEnd returns. Copy
            # it while the hook still owns a live path; the detached worker then
            # reads this private snapshot instead of racing the archive operation.
            with tempfile.NamedTemporaryFile("wb", suffix=".jsonl", prefix="codex-transcript-",
                                             dir=payload_dir, delete=False) as snapshot_file:
                snapshot = Path(snapshot_file.name)
                created.append(snapshot)
                with Path(transcript).open("rb") as source_file:
                    shutil.copyfileobj(source_file, snapshot_file)
            data = dict(data)
            data["transcript_path"] = str(snapshot)
            data["_delegation_core_snapshot_path"] = str(snapshot)
        with tempfile.NamedTemporaryFile("w", suffix=".json", prefix="codex-",
                                         dir=payload_dir, delete=False, encoding="utf-8") as fh:
            payload = Path(fh.name)
            created.append(payload)
            json.dump(data, fh)
        subprocess.Popen(
            [sys.executable, "-m", "delegation_core.hooks.entrada", "session-end-file", str(payload)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            **_detached_popen_kwargs(),
        )
    except Exception as e:
        # No worker will ever clean these up, and one of them holds the raw,
        # unredacted transcript.
        for leftover in created:
            try:
                leftover.unlink(missing_ok=True)
            except OSError:
                pass
        sys.stderr.write(f"delegation-core-hook: codex session dispatch failed: {type(e).__name__}: {e}\n")


def _payload_dir() -> Path:
    from ..config import CONFIG_DIR
    return CONFIG_DIR / "session_hook_payloads"


def _inside_payload_dir(path: Path) -> bool:
    try:
        path.resolve().relative_to(_payload_dir().resolve())
        return True
    except (ValueError, OSError):
        return False


#: A worker that never ran (reboot, kill, a failed spawn) leaves its payload and
#: a raw transcript snapshot behind. A live worker finishes in seconds, so
#: anything this old is an orphan.
STALE_PAYLOAD_SECONDS = 24 * 3600


def _sweep_stale_payloads(payload_dir: Path, now: float | None = None) -> None:
    moment = time.time() if now is None else now
    try:
        entries = list(payload_dir.glob("codex-*"))
    except OSError:
        return
    for entry in entries:
        try:
            if moment - entry.stat().st_mtime > STALE_PAYLOAD_SECONDS:
                entry.unlink()
        except OSError:
            pass


def session_end_file(payload: str) -> None:
    path = Path(payload)
    if not _inside_payload_dir(path):
        sys.stderr.write("delegation-core-hook: refusing a session payload outside the payload directory\n")
        return
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
        if isinstance(snapshot_path, str) and _inside_payload_dir(Path(snapshot_path)):
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
