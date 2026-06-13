"""Scan a whole repo for hardening targets — no file/function needed from the user.

Given just a repo (local path or GitHub URL), this walks every supported source file,
extracts top-level functions, and keeps the ones the loop can actually test today:
self-contained functions whose file compiles/loads standalone (the free, no-LLM gate in
each runner's `compiles`). Only the survivors cost an LLM call, to generate their mutants.

Returns fixture-shaped targets the existing loop already understands, one per function.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

import acquire

SUPPORTED = {".py", ".ts", ".tsx"}
SKIP_DIRS = {"node_modules", "dist", "build", "out", "__pycache__", ".venv", "venv",
             "vendor", "tests", "test", "__tests__", "examples", "fixtures"}
PY_FN = re.compile(r"^def\s+(\w+)\s*\(", re.MULTILINE)
TS_FN = re.compile(r"export\s+(?:async\s+)?function\s+(\w+)\s*\(")
BRANCH = re.compile(r"(\bif\b|\bfor\b|\bwhile\b|\belif\b|\bcase\b|\bcatch\b|\bexcept\b|\bswitch\b|\breturn\b|\?\.|&&|\|\|)")


def _log(verbose: bool, message: str) -> None:
    if verbose:
        print("[discover] " + message);


@contextmanager
def materialize_repo(repo: str) -> Iterator[Path]:
    """Yield a local directory for `repo` — the dir itself if local, else a shallow clone."""
    local = Path(repo).expanduser();
    if local.is_dir():
        yield local;
        return
    repo_id = acquire._parse_repo(repo);
    with tempfile.TemporaryDirectory(prefix="discover-") as tmp:
        clone_url = "https://github.com/{}.git".format(repo_id);
        proc = subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, tmp],
            capture_output=True, text=True, timeout=240,
        );
        if proc.returncode != 0:
            raise RuntimeError("git clone failed for {}: {}".format(repo_id, proc.stderr.strip()[:200]));
        yield Path(tmp)


def _is_test_file(name: str) -> bool:
    lowered = name.lower();
    return (
        ".test." in lowered or ".spec." in lowered or lowered.endswith(".d.ts")
        or lowered.startswith("test_") or lowered.endswith("_test.py")
    )


def iter_source_files(root: Path) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")];
        for name in sorted(filenames):
            path = Path(dirpath) / name;
            if path.suffix in SUPPORTED and not _is_test_file(name):
                yield path


def candidate_functions(src: str, language: str) -> List[str]:
    names = TS_FN.findall(src) if language == "typescript" else PY_FN.findall(src);
    ordered = [];
    for n in names:
        if not n.startswith("_") and n not in ordered:
            ordered.append(n);
    return ordered


def _function_span(src: str, name: str, language: str) -> str:
    """Best-effort slice of just the named function's source, for complexity scoring."""
    if language == "typescript":
        m = re.search(r"(?:export\s+)?(?:async\s+)?function\s+" + re.escape(name) + r"\s*\(", src);
        if not m:
            return ""
        brace = src.find("{", m.end());
        if brace < 0:
            return ""
        depth = 0;
        for idx in range(brace, len(src)):
            if src[idx] == "{":
                depth += 1;
            elif src[idx] == "}":
                depth -= 1;
                if depth == 0:
                    return src[m.start():idx + 1]
        return src[m.start():]
    lines = src.splitlines();
    for i, line in enumerate(lines):
        if re.match(r"\s*def\s+" + re.escape(name) + r"\s*\(", line):
            indent = len(line) - len(line.lstrip());
            body = [line];
            for nxt in lines[i + 1:]:
                if nxt.strip() and (len(nxt) - len(nxt.lstrip())) <= indent:
                    break
                body.append(nxt);
            return "\n".join(body)
    return ""


def _complexity(span: str) -> int:
    """Cheap static score: real logic (branches, length) ranks above trivial printers."""
    if not span:
        return 0
    body_lines = [l for l in span.splitlines() if l.strip()];
    return len(body_lines) + 2 * len(BRANCH.findall(span))


def discover_targets(
    repo: str,
    mutants_per: int = 5,
    max_targets: int = 0,
    only_file: Optional[str] = None,
    verbose: bool = True,
) -> List[Tuple[str, acquire.Target]]:
    """Find every self-contained function in `repo` and build a target for each.

    max_targets=0 means unbounded (harden every eligible function). only_file scopes the
    scan to one path. Each returned tuple is (relative_path, Target).
    """
    targets: List[Tuple[str, acquire.Target]] = [];
    with materialize_repo(repo) as root:
        files = [f for f in iter_source_files(root)];
        if only_file:
            wanted = (root / only_file).resolve();
            files = [f for f in files if f.resolve() == wanted];
        _log(verbose, "scanning {} source file(s) under {}".format(len(files), repo));

        # Pass 1 (free, no LLM): collect every eligible (self-contained) function and
        # score it. We rank before spending any tokens so the best targets go first —
        # a trivial entry point never crowds out the real logic when max_targets is small.
        candidates = [];
        for path in files:
            try:
                language = acquire._language_for(str(path));
            except ValueError:
                continue
            src = path.read_text(errors="ignore");
            names = candidate_functions(src, language);
            if not names:
                continue
            compiles = acquire._compiles_fn(language);
            # One standalone compile decides the whole file: if it loads, its top-level
            # functions are importable; if it needs sibling imports, skip it.
            if not any(compiles(src, n) for n in names[:3]):
                continue
            rel = str(path.relative_to(root));
            for name in names:
                candidates.append({
                    "rel": rel, "src": src, "language": language, "name": name,
                    "score": _complexity(_function_span(src, name, language)),
                });
        candidates.sort(key=lambda c: c["score"], reverse=True);
        _log(verbose, "{} eligible function(s); ranking by complexity".format(len(candidates)));

        # Pass 2: generate mutants best-first, stopping at max_targets.
        for c in candidates:
            if max_targets and len(targets) >= max_targets:
                _log(verbose, "reached max_targets={} -> stopping".format(max_targets));
                break
            try:
                mutants = acquire.generate_mutants(c["src"], c["name"], c["language"], mutants_per);
            except Exception as exc:
                _log(verbose, "skipping {}::{} (mutant-gen failed: {})".format(c["rel"], c["name"], exc));
                continue
            if not mutants:
                continue
            targets.append((c["rel"], acquire.Target(c["src"], mutants, c["language"], c["name"])));
            _log(verbose, "target {}::{} (score {}, {} mutants)".format(c["rel"], c["name"], c["score"], len(mutants)));
    _log(verbose, "{} target(s) with valid mutants".format(len(targets)));
    return targets
