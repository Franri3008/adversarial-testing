# Adversarial test-hardening report

## Target

| | |
|---|---|
| repo | `fiberplane/honcpiler` |
| file | `src/vfs/utils/parse-package-with-version.ts` |
| function | `parsePackageWithVersion` |
| language | typescript |
| strategy model | `claude-opus-4-8` |
| bulk model | `Qwen/Qwen3-30B-A3B-Instruct-2507` |

## Result

![convergence](convergence.png)

- **Baseline (one cold-start test):** 0% kill rate
- **Final (hardened suite):** 80% kill rate over 10 mutants
- **Gain from looping:** +80%
- **Co-evolution:** 1 adversary round(s); 8 distinct bugs caught across waves
  (the adversary kept inventing bugs the suite missed; each wave is a dip-then-recover in the graph above)
- **Tokens spent:** 30,994
- **Cost:** $0.2173

## Progress per iteration

| iter | tier | cum. tokens | kill rate | killed this round |
|---|---|---|---|---|
| 1 | bulk | 1,252 | 0% | — |
| 2 | bulk | 2,438 | 0% | — |
| 3 | bulk | 3,564 | 0% | — |
| 4 | bulk | 4,658 | 0% | — |
| 5 | strategy | 6,291 | 80% | scope_end_off_by_one, version_include_at, wrong_default_version, flipped_scope_guard |
| 6 | strategy | 7,401 | 100% | lastindexof_at |
| 7 | bulk | 17,448 | 50% | — |
| 8 | bulk | 18,666 | 50% | — |
| 9 | bulk | 23,397 | 50% | — |
| 10 | bulk | 24,650 | 50% | — |
| 11 | strategy | 26,491 | 80% | r1_scope_version_lastindexof, r1_regular_empty_version_default, r1_scope_at_zero_treated_no_version |
| 12 | strategy | 27,986 | 80% | — |
| 13 | strategy | 29,491 | 80% | — |
| 14 | strategy | 30,994 | 80% | — |

## Mutants still surviving

- `r1_empty_string_scope_check` — Uses lastIndexOf for scope slash, breaks deeper paths but not tested cases
- `r1_empty_input_no_guard` — Empty string returns name '' version 'latest' but uses charAt(0) startsWith which differs subtly on edge - actually treats empty as regular silently

## Generated adversarial tests (the changes)

The loop wrote 3 test(s) into this suite:

- [`adversarial_test_01.ts`](tests/adversarial_test_01.ts)
- [`adversarial_test_02.ts`](tests/adversarial_test_02.ts)
- [`adversarial_test_03.ts`](tests/adversarial_test_03.ts)
