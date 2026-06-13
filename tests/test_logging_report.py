import json
import sys

import llm
import main as harden_main
import repair_main
import report
from harness import (
    fix_accepted,
    fix_rejected,
    iteration_completed,
    mutants_generated,
    run_finished,
    run_started,
)
from fixtures.buggy import BUGGY_SRC, MUTANTS as SEED_MUTANTS, ONESHOT_SRC, PLANTED_BUGS, REFERENCE_SRC


def test_hardening_run_writes_structured_log(monkeypatch, tmp_path):
    log_path = tmp_path / "run.jsonl"
    monkeypatch.setattr(llm, "BACKEND", "stub")
    monkeypatch.setattr(harden_main, "LOG_PATH", str(log_path))
    monkeypatch.setattr(harden_main, "MAX_ITERATIONS", 4)
    monkeypatch.setattr(sys, "argv", ["main.py"])
    monkeypatch.setattr(report, "write_report", lambda *args, **kwargs: str(tmp_path / "report.md"))

    harden_main.main()

    entries = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert entries[0]["event"] == "run_started"
    assert any(entry["event"] == "mutants_generated" and entry["mutants"][0]["src"] for entry in entries)
    iteration_events = [entry for entry in entries if entry.get("event") == "iteration_completed"]
    assert iteration_events
    assert "generated_test_src" in iteration_events[0]
    assert "surviving_mutants" in iteration_events[-1]
    final = entries[-1]
    assert final["event"] == "run_finished"
    assert final["stop_reason"] in {"all_killed", "plateau", "max_iterations", "cost_cap", "token_cap"}
    assert "kill_rate" in final


def test_repair_run_records_fix_and_final_code(monkeypatch):
    monkeypatch.setattr(llm, "BACKEND", "stub")

    result = repair_main.run_repair(
        BUGGY_SRC,
        REFERENCE_SRC,
        PLANTED_BUGS,
        verbose=False,
        oneshot_src=ONESHOT_SRC,
        eval_mutants=list(SEED_MUTANTS),
    )

    entries = result["entries"]
    accepted = [entry for entry in entries if entry.get("event") == "fix_accepted"]
    attempted = [entry for entry in entries if entry.get("event") == "fix_attempted"]
    hardened = [entry for entry in entries if entry.get("event") == "hardening_completed"]
    final = entries[-1]
    assert accepted
    assert attempted
    assert hardened
    assert accepted[0]["bug"]["id"]
    assert accepted[0]["generated_test_src"]
    assert accepted[-1]["final_code"] == result["final_code"]
    assert final["event"] == "run_finished"
    assert final["final_code"] == result["final_code"]


def test_report_renders_new_schema(tmp_path):
    run_id = "report-test"
    mutant = {"id": "M_sub", "description": "subtracts", "src": "def add(a, b):\n    return a - b\n"}
    fixed = "def add(a, b):\n    return a + b\n"
    entries = [
        run_started(run_id, "harden", {"repo": "fixture", "file": "-", "function": "add", "language": "python"}),
        mutants_generated(run_id, "harden", [mutant]),
        iteration_completed(
            run_id,
            "harden",
            1,
            50,
            1.0,
            ["M_sub"],
            [],
            tier="bulk",
            killed_mutants=[{**mutant, "status": "killed"}],
            generated_test_src="def test_add(add):\n    assert add(1, 2) == 3\n",
        ),
        fix_accepted(
            run_id,
            "repair",
            1,
            {"id": "B1", "description": "wrong operator"},
            "def test_add(add):\n    assert add(1, 2) == 3\n",
            fixed,
            75,
        ),
        fix_rejected(
            run_id,
            "repair",
            2,
            {"id": "B2", "description": "bad edge"},
            "test_did_not_expose_bug",
            90,
        ),
        run_finished(run_id, "harden", "completed", "all_killed", 100, kill_rate=1.0),
    ]

    path = report.write_report({}, entries, [], out_dir=str(tmp_path / "report"))
    markdown = (tmp_path / "report" / "report.md").read_text()
    assert path.endswith("report.md")
    assert "## Run status" in markdown
    assert "## Mutants generated" in markdown
    assert "`M_sub`" in markdown
    assert "## Fixes accepted" in markdown
    assert "wrong operator" in markdown
    assert "test_did_not_expose_bug" in markdown
    assert "**Stop reason:** `all_killed`" in markdown


def test_report_tolerates_old_schema(tmp_path):
    entries = [{"iteration": 1, "cumulative_tokens": 10, "kill_rate": 0.5, "killed_this_round": ["M1"]}]

    report.write_report({"total_mutants": 2, "language": "python"}, entries, [], out_dir=str(tmp_path / "old"))
    markdown = (tmp_path / "old" / "report.md").read_text()
    assert "50%" in markdown
    assert "Progress per iteration" in markdown
