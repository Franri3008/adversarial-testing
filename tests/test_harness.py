"""Metrics + logging: kill-rate, plateau detection, log entries, JSONL writer."""
import json

from harness import (
    JsonlLogger,
    compute_kill_rate,
    fix_attempted,
    is_plateau,
    make_log_entry,
    mutants_generated,
    run_finished,
)


def test_compute_kill_rate():
    assert compute_kill_rate(2, 4) == 0.5
    assert compute_kill_rate(0, 0) == 0.0
    assert compute_kill_rate(5, 5) == 1.0


def test_is_plateau_needs_full_window():
    # patience=3 → needs at least 4 samples before it can report a plateau.
    assert is_plateau([1.0, 1.0, 1.0]) is False
    assert is_plateau([0.5, 0.5, 0.5, 0.5]) is True
    assert is_plateau([0.0, 0.25, 0.5, 1.0]) is False


def test_make_log_entry_shape():
    entry = make_log_entry(3, 1234, 0.75, ["M1", "M2"])
    assert entry == {
        "iteration": 3,
        "cumulative_tokens": 1234,
        "kill_rate": 0.75,
        "killed_this_round": ["M1", "M2"],
    }


def test_jsonl_logger_writes_lines(tmp_path):
    path = tmp_path / "run.jsonl"
    logger = JsonlLogger(str(path))
    logger.append({"iteration": 1, "kill_rate": 0.5})
    logger.append({"iteration": 2, "kill_rate": 1.0})
    lines = path.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[1])["kill_rate"] == 1.0
    assert len(logger.entries) == 2


def test_event_builders_preserve_full_artifacts(tmp_path):
    path = tmp_path / "run.jsonl"
    logger = JsonlLogger(str(path), run_id="run-test")
    mutant_src = "def add(a, b):\n    return a - b\n"
    fix_src = "def add(a, b):\n    return a + b\n"

    logger.append(mutants_generated(
        logger.run_id,
        "harden",
        [{"id": "M_sub", "description": "subtracts", "src": mutant_src}],
    ))
    logger.append(fix_attempted(
        logger.run_id,
        "repair",
        1,
        {"id": "B1", "description": "bad add"},
        0,
        "def test_add(add):\n    assert add(1, 2) == 3\n",
        fix_src,
        123,
    ))
    logger.append(run_finished(logger.run_id, "repair", "completed", "all_fixed", 123, final_code=fix_src))

    entries = [json.loads(line) for line in path.read_text().splitlines()]
    assert {entry["run_id"] for entry in entries} == {"run-test"}
    assert all(entry["timestamp"].endswith("Z") for entry in entries)
    assert entries[0]["mutants"][0]["src"] == mutant_src
    assert entries[1]["proposed_fixed_src"] == fix_src
    assert entries[2]["stop_reason"] == "all_fixed"
