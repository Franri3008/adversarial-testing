"""Metrics + logging: kill-rate, plateau detection, log entries, JSONL writer."""
import json

from harness import JsonlLogger, compute_kill_rate, is_plateau, make_log_entry


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
