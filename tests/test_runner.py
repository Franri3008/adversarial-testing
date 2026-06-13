"""Ground-truth runner: kill detection, the reference-must-pass gate, and a regression
test for the stale-`.pyc` multi-mutant bug (item B)."""
import runner

REFERENCE = "def add(a, b):\n    return a + b\n"

# Fixture-style test (takes `add` as a pytest fixture, per CONFTEST_TMPL).
GOOD_TEST = (
    "def test_add(add):\n"
    "    assert add(2, 3) == 5\n"
    "    assert add(0, 0) == 0\n"
)

M_SUB = {"id": "M_sub", "description": "subtracts", "src": "def add(a, b):\n    return a - b\n"}
M_PLUS1 = {"id": "M_plus1", "description": "off by one", "src": "def add(a, b):\n    return a + b + 1\n"}
M_IDENTICAL = {"id": "M_identical", "description": "same as reference", "src": REFERENCE}


def test_kills_only_the_failing_mutants():
    # Three mutants in ONE call: two diverge and must be killed, one is identical to the
    # reference and must NOT be reported killed. A stale-`.pyc` regression would corrupt this.
    result = runner.run_and_check(GOOD_TEST, REFERENCE, [M_SUB, M_PLUS1, M_IDENTICAL])
    assert result["reference_passed"] is True
    assert set(result["killed_mutant_ids"]) == {"M_sub", "M_plus1"}


def test_bad_test_trusts_no_kills():
    # A test that fails on the correct reference is a bad test: reference_passed is False
    # and none of its "kills" are trusted.
    bad_test = "def test_add(add):\n    assert add(2, 3) == 999\n"
    result = runner.run_and_check(bad_test, REFERENCE, [M_SUB])
    assert result["reference_passed"] is False
    assert result["killed_mutant_ids"] == []


def test_no_mutants_short_circuits():
    result = runner.run_and_check(GOOD_TEST, REFERENCE, [])
    assert result == {"reference_passed": True, "killed_mutant_ids": []}


def test_compiles_smoke():
    assert runner.compiles(REFERENCE, "add") is True
    assert runner.compiles("def other():\n    return 1\n", "add") is False
    assert runner.compiles("def add(a, b)\n    return a + b\n", "add") is False  # syntax error
