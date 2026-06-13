"""Scan a whole repo for hardening targets — no file/function needed from the user.

Given just a repo (local path or GitHub URL), this walks every supported source file,
extracts top-level functions, and keeps the ones the loop can actually test today:
self-contained functions whose file compiles/loads standalone (the free, no-LLM gate in
each runner's `compiles`). Only the survivors cost an LLM call, to generate their mutants.

Returns fixture-shaped targets the existing loop already understands, one per function.
"""
from __future__ import annotations

import logging
import json
import os
import re
import shutil
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

import acquire
import llm

SUPPORTED = {".py", ".ts", ".tsx"}
SKIP_DIRS = {"node_modules", "dist", "build", "out", "__pycache__", ".venv", "venv",
             "vendor", "tests", "test", "__tests__", "examples", "fixtures"}
PY_FN = re.compile(r"^def\s+(\w+)\s*\(", re.MULTILINE)
TS_FN = re.compile(r"export\s+(?:async\s+)?function\s+(\w+)\s*\(")
BRANCH = re.compile(r"(\bif\b|\bfor\b|\bwhile\b|\belif\b|\bcase\b|\bcatch\b|\bexcept\b|\bswitch\b|\breturn\b|\?\.|&&|\|\|)")


def _build_logger() -> logging.Logger:
    """A pretty, loggable channel for discover output.

    Console gets a timestamped, tagged line; set ADVERSARIAL_LOG_FILE to also append every
    line to a file. Configured once and idempotent so importing this module twice is safe.
    """
    log = logging.getLogger("adversarial.discover");
    if getattr(log, "_configured", False):
        return log
    log.setLevel(logging.INFO);
    log.propagate = False;
    fmt = logging.Formatter("%(asctime)s [discover] %(message)s", datefmt="%H:%M:%S");
    console = logging.StreamHandler();
    console.setFormatter(fmt);
    log.addHandler(console);
    log_file = os.environ.get("ADVERSARIAL_LOG_FILE");
    if log_file:
        file_handler = logging.FileHandler(Path(log_file).expanduser(), encoding="utf-8");
        file_handler.setFormatter(logging.Formatter("%(asctime)s [discover] %(message)s"));
        log.addHandler(file_handler);
    log._configured = True;  # type: ignore[attr-defined]
    return log


logger = _build_logger()


def _log(verbose: bool, message: str) -> None:
    if verbose:
        logger.info(message);


def _cache_root() -> Path:
    """Where cached clones live; override with ADVERSARIAL_REPO_CACHE."""
    base = os.environ.get("ADVERSARIAL_REPO_CACHE");
    if base:
        return Path(base).expanduser();
    return Path.home() / ".cache" / "adversarial-testing" / "repos"


def _reset_cached_repo(path: Path) -> bool:
    """Drop any local changes and reset a cached clone to its primary branch.

    Returns True if `path` is a usable git checkout that was reset, False otherwise
    (caller should then clone fresh). A shallow clone has its default branch checked
    out, so `reset --hard` + `clean -fd` restores it to the downloaded state.
    """
    if not (path / ".git").is_dir():
        return False
    for cmd in (["git", "reset", "--hard"], ["git", "clean", "-fd"]):
        proc = subprocess.run(cmd, cwd=str(path), capture_output=True, text=True, timeout=120);
        if proc.returncode != 0:
            return False
    return True


@contextmanager
def materialize_repo(repo: str) -> Iterator[Path]:
    """Yield a local directory for `repo` — the dir itself if local, else a cached shallow clone.

    Clones are cached on disk under _cache_root(), so a repo downloaded once is reused: on
    reuse we just drop local changes and reset to its primary branch instead of re-cloning.
    """
    local = Path(repo).expanduser();
    if local.is_dir():
        yield local;
        return
    repo_id = acquire._parse_repo(repo);
    dest = _cache_root() / repo_id.replace("/", "__");
    if _reset_cached_repo(dest):
        yield dest;
        return
    # Not cached yet (or a broken checkout) — clone fresh into the cache.
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True);
    dest.parent.mkdir(parents=True, exist_ok=True);
    clone_url = "https://github.com/{}.git".format(repo_id);
    proc = subprocess.run(
        ["git", "clone", "--depth", "1", clone_url, str(dest)],
        capture_output=True, text=True, timeout=240,
    );
    if proc.returncode != 0:
        shutil.rmtree(dest, ignore_errors=True);
        raise RuntimeError("git clone failed for {}: {}".format(repo_id, proc.stderr.strip()[:200]));
    yield dest


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


def _llm_rank(repo: str, candidates: List[dict], verbose: bool) -> List[dict]:
    """Let the strategy model order the eligible functions — the agent picks what to harden.

    The complexity score is only a pre-filter (cap the menu) and the fallback when no LLM is
    reachable. The actual choice is the model's: it favors functions with real logic / edge
    cases and sinks trivial wrappers, which is what the heuristic could not judge.
    """
    pool = sorted(candidates, key=lambda c: c["score"], reverse=True);
    head = pool[:60];  # cap the menu so the prompt stays small
    listing = "\n".join("{}. {}::{}".format(i, c["rel"], c["name"]) for i, c in enumerate(head));
    prompt = (
        "You are choosing which functions in the repo `{}` are most worth hardening with\n"
        "adversarial mutation tests. Favor functions with real logic and edge cases — parsing,\n"
        "comparison, validation, math, encoding, security-relevant behavior. Rank trivial\n"
        "getters, wrappers, and formatters last. You are judging by name and path only.\n\n"
        "<functions>\n{}\n</functions>\n\n"
        "Rank ALL of them. Return ONLY a JSON array of the item numbers, best first, "
        "e.g. [3, 0, 7]."
    ).format(repo, listing);
    order: List[int] = [];
    try:
        text = llm.complete(prompt, role="strategy").get("text", "");
        m = re.search(r"\[[\d,\s]*\]", text);
        if m:
            order = [int(x) for x in json.loads(m.group(0))];
    except Exception:
        order = [];
    if not order:
        _log(verbose, "LLM ranking unavailable -> falling back to complexity score");
        return pool

    seen = set();
    ranked = [];
    for idx in order:
        if 0 <= idx < len(head) and idx not in seen:
            seen.add(idx);
            ranked.append(head[idx]);
    for i, c in enumerate(head):  # any the model omitted, in complexity order
        if i not in seen:
            ranked.append(c);
    ranked.extend(pool[60:]);
    if ranked:
        _log(verbose, "LLM ranked targets; top pick {}::{}".format(ranked[0]["rel"], ranked[0]["name"]));
    return ranked


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
        candidates = _llm_rank(repo, candidates, verbose);
        _log(verbose, "{} eligible function(s); ranked by the strategy model".format(len(candidates)));

        # Pass 2: generate mutants best-first, stopping at max_targets.
        planned = min(max_targets, len(candidates)) if max_targets else len(candidates);
        for i, c in enumerate(candidates):
            if max_targets and len(targets) >= max_targets:
                _log(verbose, "reached max_targets={} -> stopping".format(max_targets));
                break
            fn = "{}::{}".format(c["rel"], c["name"]);
            _log(verbose, "[{}/{}] → generating {} mutants for {} (score {})  [LLM]…".format(
                len(targets) + 1, planned, mutants_per, fn, c["score"]));
            started = time.perf_counter();
            try:
                mutants = acquire.generate_mutants(c["src"], c["name"], c["language"], mutants_per);
            except Exception as exc:
                _log(verbose, "    ✗ {} skipped after {:.1f}s (mutant-gen failed: {})".format(
                    fn, time.perf_counter() - started, exc));
                continue
            if not mutants:
                _log(verbose, "    ✗ {} skipped after {:.1f}s (no valid mutants)".format(
                    fn, time.perf_counter() - started));
                continue
            targets.append((c["rel"], acquire.Target(c["src"], mutants, c["language"], c["name"])));
            _log(verbose, "    ✓ {}  {} mutants in {:.1f}s".format(
                fn, len(mutants), time.perf_counter() - started));
    _log(verbose, "{} target(s) with valid mutants".format(len(targets)));
    return targets
