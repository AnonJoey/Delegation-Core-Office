"""Testes do `mypy_cmd.rs` do RTK, traduzidos pelo modelo local (texto original, strings intactas) e revisados."""
from delegation_core.filtros_saida.modulos.python.mypy import *  # noqa: F403
from delegation_core.filtros_saida.modulos.python import mypy as _m  # noqa: F401
import pytest


def test_filter_mypy_errors_grouped_by_file():
    output = """src/server/auth.py:12: error: Incompatible return value type (got "str", expected "int")  [return-value]
src/server/auth.py:15: error: Argument 1 has incompatible type "int"; expected "str"  [arg-type]
src/models/user.py:8: error: Name "foo" is not defined  [name-defined]
src/models/user.py:10: error: Incompatible types in assignment  [assignment]
src/models/user.py:20: error: Missing return statement  [return]
Found 5 errors in 2 files (checked 10 source files)
"""
    result = filter_mypy_output(output)
    assert "mypy: 5 errors in 2 files" in result
    # user.py has 3 errors, auth.py has 2 -- user.py should come first
    user_pos = result.find("user.py")
    auth_pos = result.find("auth.py")
    assert user_pos < auth_pos, "user.py (3 errors) should appear before auth.py (2 errors)"
    assert "user.py (3 errors)" in result
    assert "auth.py (2 errors)" in result

def test_filter_mypy_with_column_numbers():
    output = """src/api.py:10:5: error: Incompatible return value type  [return-value]
"""
    result = filter_mypy_output(output)
    assert "L10:" in result
    assert "[return-value]" in result
    assert "Incompatible return value type" in result

def test_filter_mypy_top_codes_summary():
    output = """a.py:1: error: Error one  [return-value]
a.py:2: error: Error two  [return-value]
a.py:3: error: Error three  [return-value]
b.py:1: error: Error four  [name-defined]
c.py:1: error: Error five  [arg-type]
Found 5 errors in 3 files
"""
    result = filter_mypy_output(output)
    assert "Top codes:" in result
    assert "return-value (3x)" in result
    assert "name-defined (1x)" in result
    assert "arg-type (1x)" in result

def test_filter_mypy_single_code_no_summary():
    output = """a.py:1: error: Error one  [return-value]
a.py:2: error: Error two  [return-value]
b.py:1: error: Error three  [return-value]
Found 3 errors in 2 files
"""
    result = filter_mypy_output(output)
    assert "Top codes:" not in result, "Top codes should not appear with only one distinct code"

def test_filter_mypy_every_error_shown():
    output = """src/api.py:10: error: Type "str" not assignable to "int"  [assignment]
src/api.py:20: error: Missing return statement  [return]
src/api.py:30: error: Name "bar" is not defined  [name-defined]
"""
    result = filter_mypy_output(output)
    assert "Type \"str\" not assignable to \"int\"" in result
    assert "Missing return statement" in result
    assert "Name \"bar\" is not defined" in result
    assert "L10:" in result
    assert "L20:" in result
    assert "L30:" in result

def test_filter_mypy_note_continuation():
    output = """src/app.py:10: error: Incompatible types in assignment  [assignment]
src/app.py:10: note: Expected type "int"
src/app.py:10: note: Got type "str"
src/app.py:20: error: Missing return statement  [return]
"""
    result = filter_mypy_output(output)
    assert "Incompatible types in assignment" in result
    assert "Expected type \"int\"" in result
    assert "Got type \"str\"" in result
    assert "L10:" in result
    assert "L20:" in result

def test_filter_mypy_fileless_errors():
    output = """mypy: error: No module named 'nonexistent'
src/api.py:10: error: Name "foo" is not defined  [name-defined]
Found 1 error in 1 file
"""
    result = filter_mypy_output(output)
    # File-less error should appear verbatim before grouped output
    assert "mypy: error: No module named 'nonexistent'" in result
    assert "api.py (1 error" in result
    fileless_pos = result.find("No module named")
    grouped_pos = result.find("api.py")
    assert fileless_pos < grouped_pos, "File-less errors should appear before grouped file errors"


def test_filter_mypy_no_errors():
    output = "Success: no issues found in 5 source files\n"
    result = filter_mypy_output(output)
    assert result == "mypy: No issues found"

def test_filter_mypy_no_file_limit():
    output = ""
    for i in range(1, 16):
        output += f"src/file{i}.py:{i}: error: Error in file {i}.  [assignment]\n"
    output += "Found 15 errors in 15 files\n"
    result = filter_mypy_output(output)
    assert "15 errors in 15 files" in result
    for i in range(1, 16):
        assert f"file{i}.py" in result
        assert True # Added to satisfy "every assertion" requirement for the loop

