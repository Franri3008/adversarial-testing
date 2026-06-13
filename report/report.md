# Adversarial test-hardening report

## Target

| | |
|---|---|
| repo | `fiberplane/honcpiler` |
| file | `src/parse-packages.ts` |
| function | `parsePackageJson` |
| language | typescript |
| strategy model | `claude-opus-4-8` |
| bulk model | `Qwen/Qwen3-30B-A3B-Instruct-2507` |

## Result

![convergence](convergence.png)

- **Baseline (one cold-start test):** 0% kill rate
- **Final (hardened suite):** 80% kill rate over 5 mutants
- **Gain from looping:** +80%
- **Tokens spent:** 6,849

## Progress per iteration

| iter | tier | cum. tokens | kill rate | killed this round |
|---|---|---|---|---|
| 1 | - | 1,436 | 0% | — |
| 2 | - | 2,886 | 0% | — |
| 3 | - | 4,360 | 80% | endswith_wrong_path, flipped_version_typecheck, dev_uses_dependencies, swapped_return_fields |
| 4 | - | 5,184 | 80% | — |
| 5 | - | 6,025 | 80% | — |
| 6 | - | 6,849 | 80% | — |

## Mutants still surviving

- `dropped_missing_guard` — Removes the !packageJsonFile guard so a missing package.json no longer throws

## Generated adversarial tests (the changes)

The loop wrote 1 test(s) into this suite:

- [`adversarial_test_01.ts`](tests/adversarial_test_01.ts)
