"""Every CLI subcommand the code defines is reachable from the parser.

cmd_embed_model existed in cli.py and was never registered, while cmd_status
printed "Rode: delegation-core embed-model <modelo>" — the CLI instructed users
to run a command it did not have, and `delegation-core embed-model` answered
"invalid choice". Same shape as the graph labeler nothing called, and as
detect's extra_excludes never being passed: a capability present in the code
with no path to it.

The parser is built inline in main() rather than by a factory, so this runs the
real entry point in a subprocess and reads argparse's own error. That also means
it checks what a user actually types.
"""

import subprocess
import sys

import pytest

from delegation_core import cli

# Top-level subcommands whose handler is cli.cmd_<name>; a dash in the command
# becomes an underscore in the function name. Grouped commands (note, graph,
# process) dispatch through their own sub-parsers and are not listed here.
EXPECTED = ["setup", "run", "service", "status", "doctor", "reindex", "maintain",
            "ingest", "relink", "search", "compress", "embed-model"]


def _run(*args):
    return subprocess.run(
        [sys.executable, "-c", "from delegation_core.cli import main; main()", *args],
        capture_output=True, text=True, timeout=120,
    )


@pytest.mark.parametrize("command", EXPECTED)
def test_subcommand_is_registered(command):
    result = _run(command, "--help")
    assert "invalid choice" not in result.stderr, (
        f"`delegation-core {command}` is not on the parser, so the "
        f"cmd_{command.replace('-', '_')} handler is unreachable."
    )


@pytest.mark.parametrize("command", EXPECTED)
def test_handler_exists_for_registered_subcommand(command):
    """The inverse: a registered command whose handler was renamed away."""
    assert hasattr(cli, f"cmd_{command.replace('-', '_')}")


def test_unknown_subcommand_is_still_rejected():
    """A parser that accepted anything would pass the checks above trivially."""
    assert "invalid choice" in _run("no-such-command").stderr


def test_cmd_status_mostra_commit_do_checkout(monkeypatch, tmp_path, capsys):
    """cmd_status mostra o commit e o branch do checkout de origem."""
    from delegation_core import config, installer

    vault = tmp_path / "vault"
    vault.mkdir()
    fake_cfg = config.Config(vault_path=str(vault), engine_mode="agent")
    monkeypatch.setattr(config.Config, "load", classmethod(lambda cls: fake_cfg))
    monkeypatch.setattr(cli, "_index_row_counts", lambda _c: ({"vault_bge_m3": 42}, "daemon"))
    monkeypatch.setattr(installer, "source_root", lambda: tmp_path)
    monkeypatch.setattr(installer, "is_git_checkout", lambda p: p == tmp_path)
    respostas = {
        ("rev-parse", "--short", "HEAD"): (0, "5c466b6"),
        ("rev-parse", "--abbrev-ref", "HEAD"): (0, "master"),
    }
    monkeypatch.setattr(installer, "_git", lambda _r, *a: respostas.get(a, (1, "")))

    cli.cmd_status(None)
    saida = capsys.readouterr().out
    assert "commit" in saida
    assert "5c466b6 (master)" in saida

