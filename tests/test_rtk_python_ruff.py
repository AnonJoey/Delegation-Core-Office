"""Testes do `ruff_cmd.rs` do RTK, traduzidos pelo modelo local (texto original, strings intactas) e revisados."""
from delegation_core.filtros_saida.modulos.python.ruff import *  # noqa: F403
from delegation_core.filtros_saida.modulos.python import ruff as _m  # noqa: F401
import pytest


def test_known_ruff_subcommands_do_not_route_through_check():
    for subcommand in RUFF_SUBCOMMANDS:
        args = [subcommand]
        assert is_check_invocation(args) == (subcommand == "check")

def test_ruff_subcommands_cover_the_ruff_cli():
    assert RUFF_SUBCOMMANDS == [
        "analyze",
        "check",
        "clean",
        "config",
        "format",
        "generate-shell-completion",
        "help",
        "linter",
        "rule",
        "server",
        "version",
    ]

def test_paths_and_explicit_check_route_through_check():
    assert is_check_invocation([])
    assert is_check_invocation(["check", "."])
    assert is_check_invocation(["src"])
    assert is_check_invocation(["pyproject.toml"])

def test_top_level_flags_are_not_misclassified_as_paths():
    assert not is_check_invocation(["--version"])
    assert not is_check_invocation(["--help"])

def test_filter_ruff_check_no_issues():
    output = "[]"
    result = filter_ruff_check_json(output)
    assert "Ruff" in result
    assert "No issues found" in result

def test_filter_ruff_check_with_issues():
    output = """[
  {
    "code": "F401",
    "message": "`os` imported but unused",
    "location": {"row": 1, "column": 8},
    "end_location": {"row": 1, "column": 10},
    "filename": "src/main.py",
    "fix": {"applicability": "safe"}
  },
  {
    "code": "F401",
    "message": "`sys` imported but unused",
    "location": {"row": 2, "column": 8},
    "end_location": {"row": 2, "column": 11},
    "filename": "src/main.py",
    "fix": null
  },
  {
    "code": "E501",
    "message": "Line too long (100 > 88 characters)",
    "location": {"row": 10, "column": 89},
    "end_location": {"row": 10, "column": 100},
    "filename": "src/utils.py",
    "fix": null
  }
]"""
    result = filter_ruff_check_json(output)
    assert "3 issues" in result
    assert "2 files" in result
    assert "1 fixable" in result
    assert "F401" in result
    assert "E501" in result
    assert "main.py" in result
    assert "utils.py" in result
    assert "Violations:" in result
    assert "1:8" in result

def test_filter_ruff_format_all_formatted():
    output = "5 files left unchanged"
    result = filter_ruff_format(output)
    assert "Ruff format" in result
    assert "All files formatted correctly" in result

def test_filter_ruff_format_needs_formatting():
    output = """Would reformat: src/main.py
Would reformat: tests/test_utils.py
2 files would be reformatted, 3 files left unchanged"""
    result = filter_ruff_format(output)
    assert "2 files need formatting" in result
    assert "main.py" in result
    assert "test_utils.py" in result
    assert "3 files already formatted" in result

def test_filter_ruff_check_caps_violations_and_emits_hint():
    diags = []
    for i in range(200):
        diags.append(
            f'  {{\n    "code": "F401",\n    "message": "`module_{i}` imported but unused",\n    "location": {{"row": {i}, "column": 4}},\n    "end_location": {{"row": {i}, "column": 20}},\n    "filename": "/Users/dev/project/src/feature_{i}.py",\n    "fix": null\n  }}'
        )
    json_str = f"[\n{',\n'.join(diags)}\n]"
    result = filter_ruff_check_json(json_str)

    in_section = result.split("Violations:")[1] if "Violations:" in result else ""
    listed = sum(1 for line in in_section.splitlines() if line.strip().startswith("src/"))
    assert listed <= 50
    assert "… +150 more" in result

    raw_tokens = len(json_str.split())
    out_tokens = len(result.split())
    savings = 100.0 - (out_tokens / raw_tokens) * 100.0
    assert savings >= 60.0


def test_compact_path():
    assert compact_path("/Users/foo/project/src/main.py") == "src/main.py"
    assert compact_path("/home/user/app/lib/utils.py") == "lib/utils.py"
    assert compact_path("C:\\Users\\foo\\project\\tests\\test.py") == "tests/test.py"
    assert compact_path("relative/file.py") == "file.py"

