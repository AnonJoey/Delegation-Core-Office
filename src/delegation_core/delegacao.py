"""Mandar trabalho de indice para o daemon que esta rodando, ou dizer que nao da."""

from __future__ import annotations

import sys


def _delegate(cfg, args, tool: str, arguments: dict, say) -> dict | None:
    """Hand index work to the running daemon; None means "do it yourself".

    Every command that touches the index goes through here. That is a claim
    about eleven functions, and listing them HERE is what made this line wrong
    twice: first for `note write`/`note update`, then — in the correction that
    named those two — for `relink` and `graph build`, which write just as much
    and were not counted. A hand-written list inside a docstring is a copy, and
    copies drift.

    `tests/test_cli_delega_escrita.py` enforces the property instead: it walks
    every `cmd_*` in this file, finds the ones that construct a VaultManager,
    and fails on any that neither delegates nor carries a written, measured
    exemption. Read that file for who is exempt and why.

    When the daemon is
    up it owns the index and the resident BGE model, so a second process opening
    the same directory is both a concurrent writer and a second ~2.4 GiB copy of
    the model on the GPU: see daemon.py for what that cost in practice, and for
    why a *failed* daemon call is not allowed to fall back to local work.

    `say` reports routing on the command's own output channel, since `maintain`
    speaks JSON on stdout and must keep it parseable.
    """
    if getattr(args, "local", False):
        return None

    from . import daemon
    from .config import CONFIG_DIR

    def _fall_back(reason: str):
        """Take the local path, or refuse it when this machine has opted out.

        Refusing exits 0, not 1: a hook that skipped a reindex on purpose has
        not failed, and a non-zero exit here would surface as an error on every
        session start. The message names the switch so the skip is legible in
        the log rather than looking like nothing happened.
        """
        if cfg.local_index_fallback_allowed():
            say(f"{reason}. Running in this process.")
            return None
        say(f"{reason}. Refusing to write the index from this process.")
        say("Local index fallback is off (config allow_local_index_fallback, or "
            f"{CONFIG_DIR / 'no_auto_reindex'}). Start the daemon, or pass --local.")
        sys.exit(0)

    if not daemon.is_listening(cfg):
        return _fall_back(f"No daemon on {cfg.server_host}:{cfg.server_port}")
    try:
        say(f"Delegating to the daemon at {cfg.server_url} ...")
        timeout = getattr(args, "timeout", None)
        return daemon.submit_and_wait(cfg, tool, arguments, timeout=timeout)
    except daemon.DaemonUnavailable as exc:
        return _fall_back(f"Daemon went away ({exc})")
    except daemon.DaemonCallFailed as exc:
        # Deliberately fatal. Retrying locally would start the second writer the
        # daemon exists to prevent, on top of a daemon that is already unwell.
        say(f"Error: {exc}")
        say("Re-run with --local to do this work in this process anyway.")
        sys.exit(1)
