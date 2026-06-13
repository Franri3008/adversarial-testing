# Adversarial test-hardening report

## Target

| | |
|---|---|
| repo | `fiberplane/honcpiler` |
| file | `src/vfs/utils/semver-compare.ts` |
| function | `getLatestVersion` |
| language | typescript |
| strategy model | `claude-opus-4-8` |
| bulk model | `Qwen/Qwen3-30B-A3B-Instruct-2507` |

## Result

![convergence](convergence.png)

- **Baseline (one cold-start test):** 0% kill rate
- **Final (hardened suite):** 80% kill rate over 5 mutants
- **Gain from looping:** +80%
- **Tokens spent:** 9,820
- **Cost:** $0.0568

## Progress per iteration

| iter | tier | cum. tokens | kill rate | killed this round |
|---|---|---|---|---|
| 1 | bulk | 1,137 | 80% | flipped_comparison, ge_instead_of_gt, wrong_initial_value, swapped_compare_args |
| 2 | bulk | 2,276 | 80% | — |
| 3 | bulk | 3,464 | 80% | — |
| 4 | bulk | 4,474 | 80% | — |
| 5 | strategy | 5,991 | 80% | — |
| 6 | strategy | 7,298 | 80% | — |
| 7 | strategy | 8,560 | 80% | — |
| 8 | strategy | 9,820 | 80% | — |

## Mutants still surviving

- `dropped_empty_guard` — Removes the empty-array guard so it returns undefined seed silently

## Generated adversarial tests (the changes)

The loop wrote 1 test(s) into this suite:

- [`adversarial_test_01.ts`](tests/adversarial_test_01.ts)
