"""Acquire a mutation-testing target from a real repo, no fixture authoring.

Given a repo (a local checkout path OR a GitHub URL) + file path + function name, this:
  1. reads that file — from local disk if `repo` is a directory, else via `gh api` (no clone),
  2. uses the file as the reference implementation,
  3. asks the strategy model to generate N realistic single-bug mutants,
  4. validates them — drops duplicates, no-ops, and anything that does not compile
     (via the language's runner.compiles), so a broken mutant can never be a false kill.

Returns a fixture-shaped target the existing loop already understands.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import llm

EXT_LANGUAGE = {".ts": "typescript", ".tsx": "typescript", ".py": "python"}


@dataclass
class Target:
    reference_src: str
    mutants: List[Dict[str, Any]]
    language: str
    function_name: str


def _parse_repo(url: str) -> str:
    """https://github.com/OWNER/NAME(.git) -> 'OWNER/NAME'."""
    m = re.search(r"github\.com[:/]+([^/]+)/([^/]+?)(?:\.git)?/?$", url.strip())
    if not m:
        # Allow a bare "owner/name" too.
        if re.fullmatch(r"[^/\s]+/[^/\s]+", url.strip()):
            return url.strip()
        raise ValueError(f"Could not parse owner/name from repo='{url}'")
    return f"{m.group(1)}/{m.group(2)}"


def _language_for(path: str) -> str:
    for ext, lang in EXT_LANGUAGE.items():
        if path.endswith(ext):
            return lang
    raise ValueError(f"Unsupported file type for '{path}' (supported: {sorted(EXT_LANGUAGE)})")


def fetch_file(repo_url: str, path: str) -> str:
    # Local checkout: if `repo` is an existing directory, read straight from disk
    # (no network, no clone) — handy when you already have the repo locally.
    local = Path(repo_url).expanduser()
    if local.is_dir():
        f = local / path
        if not f.exists():
            raise RuntimeError(f"'{path}' not found in local repo {local}")
        return f.read_text()

    repo = _parse_repo(repo_url)
    proc = subprocess.run(
        ["gh", "api", f"repos/{repo}/contents/{path}", "--jq", ".content"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode == 0:
        import base64

        return base64.b64decode(proc.stdout.strip()).decode("utf-8")

    # `gh api` failed — most often because no GitHub token is configured.
    # Fall back to a shallow, unauthenticated clone (works for public repos).
    print(f"[acquire] gh api failed ({proc.stderr.strip()[:120]}); falling back to git clone")
    return _fetch_file_via_clone(repo, path)


def _fetch_file_via_clone(repo: str, path: str) -> str:
    clone_url = f"https://github.com/{repo}.git"
    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run(
            ["git", "clone", "--depth", "1", "--filter=blob:none", clone_url, tmp],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"git clone failed for {repo}: {proc.stderr.strip()[:200]}"
            )
        f = Path(tmp) / path
        if not f.exists():
            raise RuntimeError(f"'{path}' not found in cloned repo {repo}")
        return f.read_text()


_MUTANT_PROMPT = """\
You are generating mutants for mutation testing. Below is a CORRECT {language}
implementation. The function under test is `{fn}`.

Produce {n} DISTINCT mutants. Each mutant is a FULL copy of the code with exactly ONE
small, realistic bug introduced into `{fn}` — e.g. an off-by-one, a flipped comparison,
a wrong constant/default, a dropped guard/validation, a wrong operator. Each mutant MUST
still compile/parse and keep the same function signature and exports.

Return ONLY a JSON array, no prose:
[{{"id": "<short_snake_case_id>", "description": "<one line: what bug>", "src": "<full module source>"}}]

Correct implementation:
```{language}
{ref}
```
"""


def _extract_json_array(text: str) -> List[dict]:
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m:
        raise ValueError(f"no JSON array in mutant output: {text[:200]!r}")
    blob = m.group(0)
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        # The response was likely truncated (output token cap) mid-string, so the
        # greedy regex closed on a stray ']' inside the source. Salvage every
        # complete object we can with a streaming decoder instead of crashing.
        salvaged = _salvage_objects(blob)
        if not salvaged:
            raise
        print(f"[acquire] recovered {len(salvaged)} mutant(s) from a truncated response")
        return salvaged


def _salvage_objects(blob: str) -> List[dict]:
    """Decode as many leading top-level JSON objects from an array as possible."""
    decoder = json.JSONDecoder()
    objs: List[dict] = []
    i = blob.find("{")
    while i != -1:
        try:
            obj, end = decoder.raw_decode(blob, i)
        except json.JSONDecodeError:
            break  # hit the truncated tail
        if isinstance(obj, dict):
            objs.append(obj)
        # advance to the next '{' after this object
        i = blob.find("{", end)
    return objs


def _compiles_fn(language: str):
    if language == "typescript":
        from runner_ts import compiles
    else:
        from runner import compiles
    return compiles


def generate_mutants(
    reference_src: str, function_name: str, language: str, n: int
) -> List[Dict[str, Any]]:
    prompt = _MUTANT_PROMPT.format(language=language, fn=function_name, n=n, ref=reference_src)
    # Each mutant is a full copy of the source; with JSON-escaping (newlines -> \n)
    # the output is ~2x the raw chars. Budget for n copies + overhead so the
    # response is not truncated mid-string (which corrupts the JSON).
    max_tokens = max(4096, int(len(reference_src) / 4 * n * 2) + 1024)
    response = llm.complete(prompt, role="strategy", max_tokens=max_tokens)
    candidates = _extract_json_array(response["text"])

    compiles = _compiles_fn(language)
    ref_norm = reference_src.strip()
    seen_src: set[str] = set()
    valid: List[Dict[str, Any]] = []
    for i, c in enumerate(candidates):
        src = (c.get("src") or "").strip()
        if not src or src == ref_norm or src in seen_src:
            continue  # empty, no-op, or duplicate
        if not compiles(src, function_name):
            print(f"[acquire] dropping mutant {c.get('id', i)} (does not compile)")
            continue
        seen_src.add(src)
        valid.append(
            {
                "id": c.get("id") or f"mut_{i}",
                "description": c.get("description", ""),
                "src": src,
            }
        )
    return valid


def acquire_target(repo_url: str, path: str, function_name: str, n_mutants: int = 5) -> Target:
    language = _language_for(path)
    reference_src = fetch_file(repo_url, path)
    print(f"[acquire] {repo_url} :: {path} ({language}), target `{function_name}`")

    # The reference itself must compile/export the target, else nothing downstream works.
    compiles = _compiles_fn(language)
    if not compiles(reference_src, function_name):
        raise RuntimeError(
            f"reference does not compile or export `{function_name}` in a standalone harness "
            f"(file may rely on imports). Pick a self-contained function for now."
        )

    mutants = generate_mutants(reference_src, function_name, language, n_mutants)
    if not mutants:
        raise RuntimeError("no valid mutants were generated; try a larger n or another function")
    print(f"[acquire] {len(mutants)} valid mutants: {[m['id'] for m in mutants]}")
    return Target(reference_src, mutants, language, function_name)
