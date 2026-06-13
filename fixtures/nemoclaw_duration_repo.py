"""Repo-backed NemoClaw fixture for the shields timeout duration parser.

Unlike fixtures/duration_ts.py, this reads the current source from a local
NemoClaw checkout and asks the runner to execute the generated test through
NemoClaw's own vitest project.
"""

import os
from pathlib import Path

LANGUAGE = "typescript"
RUNNER = "typescript_repo"
FUNCTION_NAME = "parseDuration"

REPO_PATH = os.environ.get("NEMOCLAW_REPO_PATH", "/Users/minhuang/Codes/NemoClaw")
TARGET_PATH = "src/lib/domain/duration.ts"
TEST_IMPORT_PATH = "./duration"
VITEST_PROJECT = "cli"


def _read_reference() -> str:
    path = Path(REPO_PATH) / TARGET_PATH
    if not path.exists():
        raise RuntimeError(
            "NemoClaw checkout not found at {}. Clone it or set NEMOCLAW_REPO_PATH.".format(
                REPO_PATH
            )
        )
    return path.read_text()


def _replace(src: str, old: str, new: str) -> str:
    if old not in src:
        raise RuntimeError("fixture mutation pattern not found: {}".format(old))
    return src.replace(old, new, 1)


def _remove_block(src: str, block: str) -> str:
    return _replace(src, block, "")


REFERENCE_SRC = _read_reference()

MUTANTS = [
    {
        "id": "M1_minute_multiplier",
        "description": "Minute multiplier is 1 instead of 60, so '5m' returns 5 not 300.",
        "src": _replace(REFERENCE_SRC, "  m: 60,\n", "  m: 1,\n"),
    },
    {
        "id": "M2_no_cap",
        "description": "SECURITY: drops the 30-minute cap, so '1h' (3600s) is accepted instead of rejected.",
        "src": _remove_block(
            REFERENCE_SRC,
            """  if (seconds > MAX_SECONDS) {
    throw new Error(
      `Duration ${seconds}s exceeds maximum of ${MAX_SECONDS}s (${MAX_SECONDS / 60} minutes)`,
    );
  }
""",
        ),
    },
    {
        "id": "M3_default_unit_minutes",
        "description": "Default unit is minutes instead of seconds, so raw '300' becomes 18000s.",
        "src": _replace(
            REFERENCE_SRC,
            '  const unit = (match[2] ?? "s").toLowerCase();',
            '  const unit = (match[2] ?? "m").toLowerCase();',
        ),
    },
    {
        "id": "M4_allow_zero",
        "description": "Drops the positivity guard, so '0' returns 0 instead of being rejected.",
        "src": _remove_block(
            REFERENCE_SRC,
            """  if (seconds <= 0) {
    throw new Error("Duration must be greater than zero");
  }
""",
        ),
    },
    {
        "id": "M5_empty_returns_default",
        "description": "Empty input returns DEFAULT_SECONDS instead of throwing.",
        "src": _replace(
            REFERENCE_SRC,
            """  if (!trimmed) {
    throw new Error("Duration cannot be empty");
  }
""",
            """  if (!trimmed) {
    return DEFAULT_SECONDS;
  }
""",
        ),
    },
]
