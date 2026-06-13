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

import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

PYTEST_TIMEOUT = 30  # seconds per implementation


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
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "test_generated.py"],
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=PYTEST_TIMEOUT,
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
    with tempfile.TemporaryDirectory(prefix="loopify-smoke-") as tmp:
        return _pytest_passes(Path(tmp), impl_src, smoke, function_name)


def run_and_check(
    test_src: str, reference_src: str, mutants: List[Dict[str, Any]]
) -> Dict[str, Any]:
    if not mutants:
        return {"reference_passed": True, "killed_mutant_ids": []}

    fn = _function_name(reference_src)

    with tempfile.TemporaryDirectory(prefix="loopify-mut-") as tmp:
        workdir = Path(tmp)

        # 1) The test must PASS on the correct reference, else it's a bad test and
        #    we trust none of its kills.
        reference_passed = _pytest_passes(workdir, reference_src, test_src, fn)
        if not reference_passed:
            return {"reference_passed": False, "killed_mutant_ids": []}

        # 2) A mutant is killed iff the same test FAILS on it.
        killed: List[str] = []
        for m in mutants:
            if not _pytest_passes(workdir, m["src"], test_src, fn):
                killed.append(m["id"])

    return {"reference_passed": True, "killed_mutant_ids": killed}
