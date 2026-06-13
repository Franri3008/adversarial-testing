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


# Regression: a module where the target is NOT the first top-level def. The runner derives
# the fixture name from the first def (`helper`) unless given the real name, so a test
# asking for the target's fixture errored "fixture not found" -> reference_passed=False ->
# 0 kills no matter how correct the test. The mutation loop hits this for any acquired/
# discovered function that isn't first in its file (e.g. harness.is_plateau).
MULTI_FN_REFERENCE = (
    "def helper(x):\n"
    "    return x + 1\n"
    "\n"
    "def target(n):\n"
    "    return n * 2\n"
)
TARGET_TEST = (
    "def test_target(target):\n"
    "    assert target(3) == 6\n"
    "    assert target(0) == 0\n"
)
M_TARGET_BUG = {
    "id": "M_target_x3",
    "description": "target multiplies by 3 instead of 2",
    "src": "def helper(x):\n    return x + 1\n\ndef target(n):\n    return n * 3\n",
}


def test_function_name_targets_non_first_def():
    # With the real target name, the reference passes and the diverging mutant is killed.
    result = runner.run_and_check(
        TARGET_TEST, MULTI_FN_REFERENCE, [M_TARGET_BUG], function_name="target"
    )
    assert result["reference_passed"] is True
    assert result["killed_mutant_ids"] == ["M_target_x3"]


def test_first_def_fallback_misses_non_first_target():
    # Without the name, the runner falls back to the first def (`helper`); the test asks for
    # a `target` fixture that does not exist -> reference fails. Documents why the mutation
    # loop must thread the real function name through to the runner.
    result = runner.run_and_check(TARGET_TEST, MULTI_FN_REFERENCE, [M_TARGET_BUG])
    assert result["reference_passed"] is False
