"""Run generated TypeScript tests inside a real checked-out repo.

This is the "real repo" counterpart to runner_ts.py. It copies the target repo
to a temporary workspace, writes the generated test beside the target file,
swaps the reference/mutant implementation in place, and lets the repo's own
vitest config decide pass/fail.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from fixtures import REPO_PATH, TARGET_PATH, TEST_IMPORT_PATH, VITEST_PROJECT

VITEST_TIMEOUT = int(os.environ.get("REPO_VITEST_TIMEOUT", "90"))


def _repo_path() -> Path:
    if not REPO_PATH:
        raise RuntimeError("repo-backed TS runner requires REPO_PATH on the fixture")
    repo = Path(REPO_PATH).resolve()
    if not repo.exists():
        raise RuntimeError("repo path does not exist: {}".format(repo))
    return repo


def _target_path(repo: Path) -> Path:
    if not TARGET_PATH:
        raise RuntimeError("repo-backed TS runner requires TARGET_PATH on the fixture")
    return repo / TARGET_PATH


def _ignore(_dir: str, names: List[str]) -> set[str]:
    skipped = {".git", "node_modules", "dist", "coverage", ".vitest"}
    return set(names).intersection(skipped)


def _copy_repo(src: Path, dst: Path) -> None:
    shutil.copytree(src, dst, ignore=_ignore)
    node_modules = src / "node_modules"
    if not node_modules.exists():
        raise RuntimeError("NemoClaw dependencies missing. Run `npm ci` in {} first.".format(src))
    os.symlink(node_modules, dst / "node_modules", target_is_directory=True)


def _env() -> Dict[str, str]:
    env = dict(os.environ)
    node_bin = os.environ.get("NODE_BIN")
    if node_bin:
        env["PATH"] = "{}:{}".format(node_bin, env.get("PATH", ""))
    return env


def _test_path_for(target: Path) -> Path:
    return target.with_name("{}.mut.test.ts".format(target.stem))


def _normalize_test_import(test_src: str) -> str:
    if not TEST_IMPORT_PATH:
        return test_src
    return test_src.replace('from "./impl"', 'from "{}"'.format(TEST_IMPORT_PATH))


def _vitest_passes(repo: Path, impl_src: str, test_src: str) -> bool:
    target = _target_path(repo)
    target.write_text(impl_src)

    test_file = _test_path_for(target)
    test_file.write_text(_normalize_test_import(test_src))
    rel_test = test_file.relative_to(repo)

    cmd = ["npx", "vitest", "run"]
    if VITEST_PROJECT:
        cmd.extend(["--project", VITEST_PROJECT])
    cmd.append(str(rel_test))

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(repo),
            env=_env(),
            capture_output=True,
            text=True,
            timeout=VITEST_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return False
    return proc.returncode == 0


def run_and_check(
    test_src: str, reference_src: str, mutants: List[Dict[str, Any]]
) -> Dict[str, Any]:
    if not mutants:
        return {"reference_passed": True, "killed_mutant_ids": []}

    source_repo = _repo_path()
    with tempfile.TemporaryDirectory(prefix="mut-repo-") as tmp:
        work_repo = Path(tmp) / source_repo.name
        _copy_repo(source_repo, work_repo)

        if not _vitest_passes(work_repo, reference_src, test_src):
            return {"reference_passed": False, "killed_mutant_ids": []}

        killed: List[str] = []
        for mutant in mutants:
            if not _vitest_passes(work_repo, mutant["src"], test_src):
                killed.append(mutant["id"])

    return {"reference_passed": True, "killed_mutant_ids": killed}
