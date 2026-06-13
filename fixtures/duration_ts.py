"""TypeScript fixture sourced from NVIDIA/NemoClaw: src/lib/domain/duration.ts.

`parseDuration` turns human durations ("5m", "90s", "1h", "300") into seconds and
enforces a hard 30-minute (1800s) cap — a "shields-down" security invariant in NemoClaw
(there is no way to disable the auto-restore timer). The mutants below each break one real
behavior; M2 violates the security cap, which a good adversarial test must catch.

Used by the loop when LOOPIFY_FIXTURE=duration_ts. Verified with the standalone vitest
runner (runner_ts.py), so the same generated test runs against the reference and each mutant.
"""

LANGUAGE = "typescript"
FUNCTION_NAME = "parseDuration"

REFERENCE_SRC = '''const MAX_SECONDS = 1800; // 30 minutes
const DEFAULT_SECONDS = 300; // 5 minutes

const DURATION_RE = /^(\\d+)\\s*(s|m|h)?$/i;

const MULTIPLIERS: Record<string, number> = { s: 1, m: 60, h: 3600 };

export function parseDuration(input: string): number {
  const trimmed = input.trim();
  if (!trimmed) {
    throw new Error("Duration cannot be empty");
  }
  const match = DURATION_RE.exec(trimmed);
  if (!match) {
    throw new Error(`Invalid duration "${trimmed}".`);
  }
  const value = Number(match[1]);
  const unit = (match[2] ?? "s").toLowerCase();
  const seconds = value * (MULTIPLIERS[unit] ?? 1);
  if (seconds <= 0) {
    throw new Error("Duration must be greater than zero");
  }
  if (seconds > MAX_SECONDS) {
    throw new Error(`Duration ${seconds}s exceeds maximum of ${MAX_SECONDS}s`);
  }
  return seconds;
}

export { MAX_SECONDS, DEFAULT_SECONDS };
'''

MUTANTS = [
    {
        "id": "M1_minute_multiplier",
        "description": "Minute multiplier is 1 instead of 60, so '5m' returns 5 not 300.",
        "src": '''const MAX_SECONDS = 1800;
const DEFAULT_SECONDS = 300;

const DURATION_RE = /^(\\d+)\\s*(s|m|h)?$/i;

const MULTIPLIERS: Record<string, number> = { s: 1, m: 1, h: 3600 };

export function parseDuration(input: string): number {
  const trimmed = input.trim();
  if (!trimmed) {
    throw new Error("Duration cannot be empty");
  }
  const match = DURATION_RE.exec(trimmed);
  if (!match) {
    throw new Error(`Invalid duration "${trimmed}".`);
  }
  const value = Number(match[1]);
  const unit = (match[2] ?? "s").toLowerCase();
  const seconds = value * (MULTIPLIERS[unit] ?? 1);
  if (seconds <= 0) {
    throw new Error("Duration must be greater than zero");
  }
  if (seconds > MAX_SECONDS) {
    throw new Error(`Duration ${seconds}s exceeds maximum of ${MAX_SECONDS}s`);
  }
  return seconds;
}

export { MAX_SECONDS, DEFAULT_SECONDS };
''',
    },
    {
        "id": "M2_no_cap",
        "description": "SECURITY: drops the 30-minute cap, so '1h' (3600s) is accepted instead of rejected.",
        "src": '''const MAX_SECONDS = 1800;
const DEFAULT_SECONDS = 300;

const DURATION_RE = /^(\\d+)\\s*(s|m|h)?$/i;

const MULTIPLIERS: Record<string, number> = { s: 1, m: 60, h: 3600 };

export function parseDuration(input: string): number {
  const trimmed = input.trim();
  if (!trimmed) {
    throw new Error("Duration cannot be empty");
  }
  const match = DURATION_RE.exec(trimmed);
  if (!match) {
    throw new Error(`Invalid duration "${trimmed}".`);
  }
  const value = Number(match[1]);
  const unit = (match[2] ?? "s").toLowerCase();
  const seconds = value * (MULTIPLIERS[unit] ?? 1);
  if (seconds <= 0) {
    throw new Error("Duration must be greater than zero");
  }
  return seconds;
}

export { MAX_SECONDS, DEFAULT_SECONDS };
''',
    },
    {
        "id": "M3_default_unit_minutes",
        "description": "Default unit is minutes instead of seconds, so a raw '300' becomes 18000s.",
        "src": '''const MAX_SECONDS = 1800;
const DEFAULT_SECONDS = 300;

const DURATION_RE = /^(\\d+)\\s*(s|m|h)?$/i;

const MULTIPLIERS: Record<string, number> = { s: 1, m: 60, h: 3600 };

export function parseDuration(input: string): number {
  const trimmed = input.trim();
  if (!trimmed) {
    throw new Error("Duration cannot be empty");
  }
  const match = DURATION_RE.exec(trimmed);
  if (!match) {
    throw new Error(`Invalid duration "${trimmed}".`);
  }
  const value = Number(match[1]);
  const unit = (match[2] ?? "m").toLowerCase();
  const seconds = value * (MULTIPLIERS[unit] ?? 1);
  if (seconds <= 0) {
    throw new Error("Duration must be greater than zero");
  }
  if (seconds > MAX_SECONDS) {
    throw new Error(`Duration ${seconds}s exceeds maximum of ${MAX_SECONDS}s`);
  }
  return seconds;
}

export { MAX_SECONDS, DEFAULT_SECONDS };
''',
    },
    {
        "id": "M4_allow_zero",
        "description": "Drops the positivity guard, so '0' returns 0 instead of being rejected.",
        "src": '''const MAX_SECONDS = 1800;
const DEFAULT_SECONDS = 300;

const DURATION_RE = /^(\\d+)\\s*(s|m|h)?$/i;

const MULTIPLIERS: Record<string, number> = { s: 1, m: 60, h: 3600 };

export function parseDuration(input: string): number {
  const trimmed = input.trim();
  if (!trimmed) {
    throw new Error("Duration cannot be empty");
  }
  const match = DURATION_RE.exec(trimmed);
  if (!match) {
    throw new Error(`Invalid duration "${trimmed}".`);
  }
  const value = Number(match[1]);
  const unit = (match[2] ?? "s").toLowerCase();
  const seconds = value * (MULTIPLIERS[unit] ?? 1);
  if (seconds > MAX_SECONDS) {
    throw new Error(`Duration ${seconds}s exceeds maximum of ${MAX_SECONDS}s`);
  }
  return seconds;
}

export { MAX_SECONDS, DEFAULT_SECONDS };
''',
    },
    {
        "id": "M5_empty_returns_default",
        "description": "Empty input returns the default 300s instead of throwing.",
        "src": '''const MAX_SECONDS = 1800;
const DEFAULT_SECONDS = 300;

const DURATION_RE = /^(\\d+)\\s*(s|m|h)?$/i;

const MULTIPLIERS: Record<string, number> = { s: 1, m: 60, h: 3600 };

export function parseDuration(input: string): number {
  const trimmed = input.trim();
  if (!trimmed) {
    return DEFAULT_SECONDS;
  }
  const match = DURATION_RE.exec(trimmed);
  if (!match) {
    throw new Error(`Invalid duration "${trimmed}".`);
  }
  const value = Number(match[1]);
  const unit = (match[2] ?? "s").toLowerCase();
  const seconds = value * (MULTIPLIERS[unit] ?? 1);
  if (seconds <= 0) {
    throw new Error("Duration must be greater than zero");
  }
  if (seconds > MAX_SECONDS) {
    throw new Error(`Duration ${seconds}s exceeds maximum of ${MAX_SECONDS}s`);
  }
  return seconds;
}

export { MAX_SECONDS, DEFAULT_SECONDS };
''',
    },
]
