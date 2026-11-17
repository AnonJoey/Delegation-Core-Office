"""Testes do porte de `find_cmd.rs` do RTK."""

import pytest

from delegation_core.filtros_saida.modulos.system import find


def test_group_by_dir():
    files = ["src/a.py", "src/b.py", "tests/test_a.py", "README.md"]
    by_dir = find.group_by_dir(files)
    assert by_dir["."] == ["README.md"]
    assert by_dir["src"] == ["a.py", "b.py"]
    assert by_dir["tests"] == ["test_a.py"]


def test_filter_find_output_format():
    raw = "src/a.py\nsrc/b.py\ntests/test_a.py\nREADME.md\n"
    out = find.filter_find_output(raw)
    assert "4F 3D:" in out
    assert "./ README.md" in out
    assert "src/ a.py b.py" in out
    assert "tests/ test_a.py" in out
    assert "ext: .py(3) .md(1)" in out


def test_filter_find_output_empty():
    assert find.filter_find_output("") == ""
    assert find.filter_find_output("\n   \n") == ""


def test_filter_find_budget_exceeded():
    files = [f"src/file_{i:03d}.py" for i in range(100)]
    raw = "\n".join(files)
    out = find.filter_find_output(raw, max_results=10)
    assert "100F 1D:" in out
    assert "+90 more" in out
    assert "file_000.py" in out
    assert "file_009.py" in out
    assert "file_010.py" not in out


def test_verbatim_actions():
    assert find.executa(["-name", "*.py"]) is True
    assert find.executa(["-exec", "rm", "{}", ";"]) is False
    assert find.executa(["-delete"]) is False
    assert find.trata(["-delete"]) is False
    assert find.trata(["src", "-type", "f"]) is True
