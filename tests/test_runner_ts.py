"""TypeScript runner smoke test — skipped unless the vitest harness is installed."""
import shutil
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parent.parent / "ts_harness"
_have_ts = shutil.which("npx") is not None and (HARNESS / "node_modules").exists()

pytestmark = pytest.mark.skipif(
    not _have_ts, reason="ts_harness not installed (run `cd ts_harness && npm install`) or npx missing"
)

REFERENCE = "export function add(a: number, b: number): number {\n  return a + b;\n}\n"
GOOD_TEST = (
    'import { add } from "./impl";\n'
    'import { test, expect } from "vitest";\n'
    'test("add", () => { expect(add(2, 3)).toBe(5); });\n'
)
M_SUB = {"id": "M_sub", "description": "subtracts",
         "src": "export function add(a: number, b: number): number {\n  return a - b;\n}\n"}


def test_ts_kill_detection():
    import runner_ts

    result = runner_ts.run_and_check(GOOD_TEST, REFERENCE, [M_SUB])
    assert result["reference_passed"] is True
    assert result["killed_mutant_ids"] == ["M_sub"]
