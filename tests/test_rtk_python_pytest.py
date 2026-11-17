"""Testes do `pytest_cmd.rs` do RTK, traduzidos pelo modelo local (texto original, strings intactas) e revisados."""
from delegation_core.filtros_saida.modulos.python.pytest import *  # noqa: F403
from delegation_core.filtros_saida.modulos.python import pytest as _m  # noqa: F401



def test_filter_pytest_all_pass():
    output = """=== test session starts ===
platform darwin -- Python 3.11.0
collected 5 items

tests/test_foo.py .....                                            [100%]

=== 5 passed in 0.50s ==="""

    result = filter_pytest_output(output)
    assert "Pytest" in result
    assert "5 passed" in result
    assert result == "Pytest: 5 passed in 0.50s"

def test_filter_pytest_with_failures():
    output = """=== test session starts ===
collected 5 items

tests/test_foo.py ..F..                                            [100%]

=== FAILURES ===
___ test_something ___

    def test_something():
>       assert False
E       assert False

tests/test_foo.py:10: AssertionError

=== short test summary info ===
FAILED tests/test_foo.py::test_something - assert False
=== 4 passed, 1 failed in 0.50s ==="""

    result = filter_pytest_output(output)
    assert "4 passed, 1 failed" in result
    assert result.startswith("Pytest: 4 passed, 1 failed in 0.50s")
    assert "test_something" in result
    assert "assert False" in result

def test_filter_pytest_multiple_failures():
    output = """=== test session starts ===
collected 3 items

tests/test_foo.py FFF                                              [100%]

=== FAILURES ===
___ test_one ___
E   AssertionError: expected 5

___ test_two ___
E   ValueError: invalid value

=== short test summary info ===
FAILED tests/test_foo.py::test_one - AssertionError: expected 5
FAILED tests/test_foo.py::test_two - ValueError: invalid value
FAILED tests/test_foo.py::test_three - KeyError
=== 3 failed in 0.20s ==="""

    result = filter_pytest_output(output)
    assert "3 failed" in result
    assert "test_one" in result
    assert "test_two" in result
    assert "expected 5" in result

def test_filter_pytest_no_tests():
    output = """=== test session starts ===
collected 0 items

=== no tests ran in 0.00s ==="""

    result = filter_pytest_output(output)
    assert "No tests collected" in result

def test_parse_summary_line():
    c = parse_summary_line("=== 5 passed in 0.50s ===")
    assert (c.passed, c.failed, c.skipped) == (5, 0, 0)
    assert c.duration == "0.50s"

    c = parse_summary_line("=== 4 passed, 1 failed in 0.50s ===")
    assert (c.passed, c.failed, c.skipped) == (4, 1, 0)
    assert c.duration == "0.50s"

    c = parse_summary_line("=== 3 passed, 1 failed, 2 skipped in 1.0s ===")
    assert (c.passed, c.failed, c.skipped) == (3, 1, 2)
    assert c.duration == "1.0s"

    c = parse_summary_line("=== 2 passed, 1 failed, 2 xfailed, 1 xpassed in 1.0s ===")
    assert (c.passed, c.failed, c.xfailed, c.xpassed) == (2, 1, 2, 1)
    assert c.duration == "1.0s"

def test_filter_pytest_quiet_mode_preserves_duration():
    output = "2 passed in 3.04s"

    assert filter_pytest_output(output) == "Pytest: 2 passed in 3.04s"

def test_filter_pytest_long_run_preserves_seconds_duration():
    output = "2 passed in 65.12s (0:01:05)"

    assert filter_pytest_output(output) == "Pytest: 2 passed in 65.12s"

def test_parse_duration_rejects_tails_that_are_not_seconds():
    assert parse_duration("=== 2 passed in 0.50s ===") == "0.50s"
    assert parse_duration("2 passed in 65.12s (0:01:05)") == "65.12s"
    assert parse_duration("=== 2 passed ===") is None
    assert parse_duration("2 passed in seconds") is None
    assert parse_duration("2 passed in 0.50") is None


def test_filter_pytest_duration_on_every_summary_shape():
    # Wrapped long-run form with a warnings part before the duration.
    output = "=== 5 passed, 2 warnings in 65.12s (0:01:05) ==="
    assert filter_pytest_output(output) == "Pytest: 5 passed in 65.12s"

    # Only-skipped run takes the multi-line emit path.
    output = "=== 3 skipped in 0.10s ==="
    assert filter_pytest_output(output) == "Pytest: 0 passed, 0 failed, 3 skipped in 0.10s"

    # Quiet-mode failures line keeps its duration on the multi-line path too.
    output = "5 failed, 1698 passed, 2 skipped in 108.89s"
    assert filter_pytest_output(output) == "Pytest: 1698 passed, 5 failed, 2 skipped in 108.89s"

def test_filter_pytest_xfail_caps_and_tee_hint():
    lines = "=== test session starts ===\ncollected 30 items\n\n"
    lines += "test_x.py "
    for _ in range(15):
        lines += 'x'
    lines += "\n\n=== short test summary info ===\n"
    for i in range(15):
        lines += f"XFAIL test_x.py::test_case_{i} - known issue #{i}\n"
    lines += "=== 0 passed, 15 xfailed in 0.05s ===\n"

    result = filter_pytest_output(lines)
    xfail_in_section = result.split("Expected-failure outcomes:")[1] if "Expected-failure outcomes:" in result else ""
    listed = sum(1 for l in xfail_in_section.splitlines() if l.strip().startswith("XFAIL"))
    assert listed <= 10, f"MAX_XFAIL cap not enforced: listed {listed}"
    assert "… +5 more" in result, f"missing '+N more': {result}"

def test_filter_pytest_xfail_xpass():
    output = """=== test session starts ===
collected 5 items

test_math.py ..xxX                                                 [100%]

=== short test summary info ===
XFAIL test_math.py::test_division_by_zero - known bug in division
XFAIL test_math.py::test_float_precision - float precision issue — bug #42
XPASS test_math.py::test_unexpected_pass - this should fail but currently passes
=== 2 passed, 2 xfailed, 1 xpassed in 0.05s ===#"""

    result = filter_pytest_output(output)
    assert "xfailed" in result, f"got: {result}"
    assert "xpassed" in result, f"got: {result}"
    assert "XPASS" in result, f"got: {result}"
    assert "float precision" in result, f"got: {result}"
    assert "test_division_by_zero" in result, f"got: {result}"

def test_filter_pytest_quiet_mode_failures():
    # In -q mode, the final summary line has NO === wrapper
    # This was causing "No tests collected" to be reported incorrectly
    output = """=== test session starts ===
platform linux -- Python 3.12.11, pytest-8.1.0
collected 1705 items

.......F.......

=== FAILURES ===
___ test_something ___

E   AssertionError: expected True

=== short test summary info ===
FAILED tests/test_foo.py::test_something - AssertionError
5 failed, 1698 passed, 2 skipped in 108.89s"""

    result = filter_pytest_output(output)
    assert "No tests collected" not in result, f"Should not report 'No tests collected' when tests ran. Got: {result}"
    assert "1698" in result or "5 failed" in result, f"Should show actual test counts. Got: {result}"

def test_filter_pytest_only_skipped():
    # If only skipped tests, should NOT say "No tests collected"
    output = """=== test session starts ===
collected 3 items

=== 3 skipped in 0.10s ===#"""

    result = filter_pytest_output(output)
    assert "No tests collected" not in result, f"Should not say 'No tests collected' when tests were skipped. Got: {result}"

