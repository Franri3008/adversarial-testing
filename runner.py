"""Real mutation-testing runner.

A mutant is "killed" when the generated test PASSES on the reference implementation
and FAILS on the mutant. This is pure ground-truth signal — no LLM judges the result,
the Python interpreter does.

The generated test receives the function under test as a pytest fixture (named after
the function defined in the reference), so the SAME test runs unchanged against the
reference and every mutant — we just swap what the fixture returns.

Isolation: each pytest invocation runs in a fresh temp dir, in a subprocess, with a
wall-clock timeout. (Container-level sandboxing is the production hardening; for the
toy fixtures the blast radius is a pure function.)
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List

PYTEST_TIMEOUT = 30  # seconds per implementation
# Auto-tune the per-mutant pytest fan-out from CPU count (mostly subprocess
# spawn + short test execution, so light oversubscription is fine). Cap at 8
# to keep combined fan-out with TARGET_WORKERS sane on big boxes.
_DEFAULT_MUTANT_WORKERS = min(os.cpu_count() or 4, 8)
MUTANT_WORKERS = max(1, int(os.environ.get("MUTANT_WORKERS", str(_DEFAULT_MUTANT_WORKERS))))


def _function_name(reference_src: str) -> str:
    m = re.search(r"^\s*def\s+(\w+)\s*\(", reference_src, re.MULTILINE)
    if not m:
        raise ValueError("could not find a top-level `def` in reference_src")
    return m.group(1)


CONFTEST_TMPL = """\
import pytest
import impl


@pytest.fixture
def {fn}():
    return impl.{fn}
"""


def _pytest_passes(workdir: Path, impl_src: str, test_src: str, fn: str) -> bool:
    """Write impl + conftest + test into workdir, run pytest, return True iff it passes."""
    (workdir / "impl.py").write_text(impl_src)
    (workdir / "conftest.py").write_text(CONFTEST_TMPL.format(fn=fn))
    (workdir / "test_generated.py").write_text(test_src)
    # All implementations in one run reuse this workdir's `impl.py`, so cached bytecode
    # could let a mutant import a stale (reference) `impl` and report a wrong kill.
    # Disable bytecode writing in the subprocess so each run always loads fresh source.
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "test_generated.py"],
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=PYTEST_TIMEOUT,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return False  # a hanging test counts as "did not pass"
    # pytest exit 0 == all passed. Anything else (failures, errors, no tests) == not passed.
    return proc.returncode == 0


def compiles(impl_src: str, function_name: str) -> bool:
    """Smoke check: does this impl import and expose `function_name` as callable?

    Used to drop LLM-generated mutants that don't compile/import, so a broken
    mutant never counts as a false 'kill'.
    """
    smoke = f"def test_loads({function_name}):\n    assert callable({function_name})\n"
    with tempfile.TemporaryDirectory(prefix="mut-smoke-") as tmp:
        return _pytest_passes(Path(tmp), impl_src, smoke, function_name)


def _check_mutant(mutant: Dict[str, Any], test_src: str, fn: str) -> bool:
    """Return True iff the test passes on this mutant (i.e. the mutant survived)."""
    with tempfile.TemporaryDirectory(prefix="mut-m-") as tmp:
        return _pytest_passes(Path(tmp), mutant["src"], test_src, fn)


def run_and_check(
    test_src: str, reference_src: str, mutants: List[Dict[str, Any]]
) -> Dict[str, Any]:
    if not mutants:
        return {"reference_passed": True, "killed_mutant_ids": []}

    fn = _function_name(reference_src)

    # 1) The test must PASS on the correct reference, else it's a bad test and
    #    we trust none of its kills.
    with tempfile.TemporaryDirectory(prefix="mut-ref-") as tmp:
        if not _pytest_passes(Path(tmp), reference_src, test_src, fn):
            return {"reference_passed": False, "killed_mutant_ids": []}

    # 2) A mutant is killed iff the same test FAILS on it. Each mutant runs in
    #    its own tempdir so parallel workers don't clobber each other's impl.py.
    workers = min(MUTANT_WORKERS, len(mutants))
    survived: Dict[str, bool] = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_check_mutant, m, test_src, fn): m["id"] for m in mutants}
        for fut in as_completed(futures):
            survived[futures[fut]] = fut.result()

    killed = [m["id"] for m in mutants if not survived[m["id"]]]
    return {"reference_passed": True, "killed_mutant_ids": killed}
