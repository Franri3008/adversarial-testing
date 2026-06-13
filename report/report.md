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
- **Final (hardened suite):** 0% kill rate over 5 mutants
- **Gain from looping:** +0%
- **Tokens spent:** 6,398

## Progress per iteration

| iter | tier | cum. tokens | kill rate | killed this round |
|---|---|---|---|---|
| 1 | - | 1,529 | 0% | — |
| 2 | - | 3,371 | 0% | — |
| 3 | - | 5,104 | 0% | — |
| 4 | - | 6,398 | 0% | — |

## Mutants still surviving

- `swap_deps` — devDependencies pushed into dependencies array (swapped target)
- `flipped_type_check` — version type check flipped to !== string, so valid string deps are skipped
- `dropped_missing_guard` — removed the !packageJsonFile guard, no error thrown when package.json missing
- `wrong_path_match` — uses startsWith instead of endsWith for nested package.json path
- `skip_devdeps_parse` — devDependencies object guard uses OR instead of AND, causing crash/wrong behavior

## Generated adversarial tests (the changes)

No tests were retained.
