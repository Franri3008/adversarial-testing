"""Active fixture selector.

Pick a fixture via env: LOOPIFY_FIXTURE=toy (default, Python) or duration_ts (TypeScript).
Each fixture module exposes REFERENCE_SRC and MUTANTS, and optionally LANGUAGE
("python" default) and FUNCTION_NAME.
"""
import importlib
import os

_name = os.environ.get("LOOPIFY_FIXTURE", "toy")
_mod = importlib.import_module(f"fixtures.{_name}")

REFERENCE_SRC = _mod.REFERENCE_SRC
MUTANTS = _mod.MUTANTS
LANGUAGE = getattr(_mod, "LANGUAGE", "python")
FUNCTION_NAME = getattr(_mod, "FUNCTION_NAME", None)
