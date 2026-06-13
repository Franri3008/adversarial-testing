"""Repair loop: the offline planted-fixture demo, and the generalized (no answer-key) path."""
import llm
import repair_main
from fixtures.buggy import BUGGY_SRC, MUTANTS as SEED_MUTANTS, ONESHOT_SRC, PLANTED_BUGS, REFERENCE_SRC


def test_fixture_demo_fixes_all_bugs(monkeypatch):
    # Locks the documented offline demo: stub backend closes all 3 planted bugs.
    monkeypatch.setattr(llm, "BACKEND", "stub")
    result = repair_main.run_repair(
        BUGGY_SRC, REFERENCE_SRC, PLANTED_BUGS,
        verbose=False, oneshot_src=ONESHOT_SRC, eval_mutants=list(SEED_MUTANTS),
    )
    assert result["graded"] == 3
    assert result["total_bugs"] == 3
    assert len(result["suite_sources"]) == 3


def test_generalized_no_oracle_does_not_crash(monkeypatch):
    # Item C regression: run_repair must work with planted_bugs=None / oracle_src=None
    # (no grading, no one-shot baseline) and never reference the missing answer key.
    monkeypatch.setattr(llm, "BACKEND", "stub")
    buggy = "def half(n):\n    return n / 2\n"
    result = repair_main.run_repair(buggy, oracle_src=None, planted_bugs=None, verbose=False)
    assert result["total_bugs"] == 0          # no planted bugs to grade against
    assert result["suite_sources"] == []      # stub strategist reports no bug → no tests
    assert result["baseline"]["total_bugs"] == 0
    assert result["final_code"] == buggy
