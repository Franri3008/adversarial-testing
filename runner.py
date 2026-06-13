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
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

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

# Package mode: the function under test isn't self-contained — it relies on
# sibling/relative imports — so we import it by its real dotted path out of a copy of
# its package, instead of loading a lone impl.py. The package dir lives next to this
# conftest; prepending its parent puts the real package name on sys.path.
PKG_CONFTEST_TMPL = """\
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
import pytest
from {module} import {fn} as _target


@pytest.fixture
def {fn}():
    return _target
"""


def _build_sandbox(workdir: Path, impl_src: str, fn: str, context: Optional[dict]) -> None:
    """Lay out impl + conftest + test in workdir for one pytest run.

    Standalone mode (context is None) writes the implementation as a lone `impl.py`.
    Package mode copies the target's top-level package into the sandbox, overwrites just
    the one file with `impl_src`, and imports the function by its real dotted path so
    relative/sibling imports resolve. We blank every `__init__.py` in the copy so a
    package whose __init__ pulls in third-party deps still imports — this is the "light"
    (no dependency install) tier; a function whose own module needs uninstalled
    third-party packages is filtered out earlier by the eligibility check.
    """
    if not context:
        (workdir / "impl.py").write_text(impl_src)
        (workdir / "conftest.py").write_text(CONFTEST_TMPL.format(fn=fn))
        return
    import_root = Path(context["import_root"])
    module = context["module"]
    target_rel = context["target_rel"]
    top_pkg = module.split(".")[0]
    shutil.copytree(
        import_root / top_pkg,
        workdir / top_pkg,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git", "tests", "test"),
    )
    for init in (workdir / top_pkg).rglob("__init__.py"):
        init.write_text("")
    (workdir / target_rel).write_text(impl_src)
    (workdir / "conftest.py").write_text(PKG_CONFTEST_TMPL.format(module=module, fn=fn))


def _pytest_passes(workdir: Path, impl_src: str, test_src: str, fn: str, context: Optional[dict] = None) -> bool:
    """Write impl + conftest + test into workdir, run pytest, return True iff it passes."""
    _build_sandbox(workdir, impl_src, fn, context)
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


def compiles(impl_src: str, function_name: str, context: Optional[dict] = None) -> bool:
    """Smoke check: does this impl import and expose `function_name` as callable?

    Used to drop LLM-generated mutants that don't compile/import, so a broken
    mutant never counts as a false 'kill'. With a package `context`, the check runs
    in the reconstructed package — so it also doubles as the eligibility gate for
    not-self-contained functions (same sandbox the loop will use).
    """
    smoke = f"def test_loads({function_name}):\n    assert callable({function_name})\n"
    with tempfile.TemporaryDirectory(prefix="mut-smoke-") as tmp:
        return _pytest_passes(Path(tmp), impl_src, smoke, function_name, context)


def _check_mutant(mutant: Dict[str, Any], test_src: str, fn: str, context: Optional[dict] = None) -> bool:
    """Return True iff the test passes on this mutant (i.e. the mutant survived)."""
    with tempfile.TemporaryDirectory(prefix="mut-m-") as tmp:
        return _pytest_passes(Path(tmp), mutant["src"], test_src, fn, context)


def run_and_check(
    test_src: str,
    reference_src: str,
    mutants: List[Dict[str, Any]],
    context: Optional[dict] = None,
    function_name: Optional[str] = None,
) -> Dict[str, Any]:
    if not mutants:
        return {"reference_passed": True, "killed_mutant_ids": []}

    # Name the pytest fixture after the ACTUAL function under test (the same name the
    # generator gave the test). Fall back to the first top-level def only when no name is
    # passed — correct only when the target IS the first def in the file.
    fn = function_name or _function_name(reference_src)

    # 1) The test must PASS on the correct reference, else it's a bad test and
    #    we trust none of its kills.
    with tempfile.TemporaryDirectory(prefix="mut-ref-") as tmp:
        if not _pytest_passes(Path(tmp), reference_src, test_src, fn, context):
            return {"reference_passed": False, "killed_mutant_ids": []}

    # 2) A mutant is killed iff the same test FAILS on it. Each mutant runs in
    #    its own tempdir so parallel workers don't clobber each other's impl.py.
    workers = min(MUTANT_WORKERS, len(mutants))
    survived: Dict[str, bool] = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_check_mutant, m, test_src, fn, context): m["id"] for m in mutants}
        for fut in as_completed(futures):
            survived[futures[fut]] = fut.result()

    killed = [m["id"] for m in mutants if not survived[m["id"]]]
    return {"reference_passed": True, "killed_mutant_ids": killed}
