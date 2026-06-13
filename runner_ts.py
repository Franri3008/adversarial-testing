"""TypeScript mutation runner — the vitest counterpart of runner.py.

Same contract as the Python runner: a mutant is "killed" when the generated test
PASSES on the reference implementation and FAILS on the mutant. Ground truth is
vitest's exit code, not any model's opinion.

It reuses a pre-installed standalone vitest project (ts_harness/) so each check is a
sub-second `npx vitest run` rather than a fresh install — and it never touches the real
NemoClaw suite. For each implementation we overwrite ts_harness/impl.ts and run the one
generated test (ts_harness/gen.test.ts), which imports `./impl`.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List

HARNESS_DIR = Path(__file__).resolve().parent / "ts_harness"
IMPL_FILE = HARNESS_DIR / "impl.ts"
TEST_FILE = HARNESS_DIR / "gen.test.ts"
VITEST_TIMEOUT = 60  # seconds per implementation


def _env() -> Dict[str, str]:
    env = dict(os.environ)
    # Optional: let callers pin a Node toolchain dir without editing PATH globally.
    node_bin = os.environ.get("NODE_BIN")
    if node_bin:
        env["PATH"] = f"{node_bin}:{env.get('PATH', '')}"
    return env


def _vitest_passes(impl_src: str, test_src: str) -> bool:
    IMPL_FILE.write_text(impl_src)
    TEST_FILE.write_text(test_src)
    try:
        proc = subprocess.run(
            ["npx", "vitest", "run", "gen.test.ts"],
            cwd=str(HARNESS_DIR),
            env=_env(),
            capture_output=True,
            text=True,
            timeout=VITEST_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return False
    return proc.returncode == 0


def compiles(impl_src: str, function_name: str) -> bool:
    """Smoke check: does this impl load and export `function_name`?

    Used to drop LLM-generated mutants that don't compile, so a broken mutant
    never counts as a false 'kill'.
    """
    smoke = (
        f'import {{ {function_name} }} from "./impl";\n'
        'import { test, expect } from "vitest";\n'
        f'test("loads", () => {{ expect(typeof {function_name}).toBe("function"); }});\n'
    )
    return _vitest_passes(impl_src, smoke)


def run_and_check(
    test_src: str, reference_src: str, mutants: List[Dict[str, Any]], function_name=None
) -> Dict[str, Any]:
    # function_name accepted for parity with the Python runner; unused (the TS test imports
    # the function by name, so there is no fixture to name).
    if not mutants:
        return {"reference_passed": True, "killed_mutant_ids": []}

    if not HARNESS_DIR.exists():
        raise RuntimeError(
            f"ts_harness not found at {HARNESS_DIR}. Run `npm install` in ts_harness first."
        )

    # 1) The test must pass on the correct reference; otherwise it is a bad test and
    #    we trust none of its kills.
    if not _vitest_passes(reference_src, test_src):
        return {"reference_passed": False, "killed_mutant_ids": []}

    # 2) A mutant is killed iff the same test fails on it.
    killed: List[str] = []
    for m in mutants:
        if not _vitest_passes(m["src"], test_src):
            killed.append(m["id"])

    return {"reference_passed": True, "killed_mutant_ids": killed}
