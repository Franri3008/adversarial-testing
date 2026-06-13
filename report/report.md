# Adversarial test-hardening report

## Target

| | |
|---|---|
| repo | `(built-in fixture)` |
| file | `-` |
| function | `-` |
| language | python |
| strategy model | `claude-opus-4-8` |
| bulk model | `Qwen/Qwen3-30B-A3B-Instruct-2507` |

## Result

![convergence](convergence.png)

- **Baseline (one cold-start test):** 40% kill rate
- **Final (hardened suite):** 100% kill rate over 5 mutants
- **Gain from looping:** +60%
- **Tokens spent:** 1,925

## Progress per iteration

| iter | tier | cum. tokens | kill rate | killed this round |
|---|---|---|---|---|
| 1 | - | 558 | 40% | M1_no_sort, M4_drop_last |
| 2 | - | 970 | 60% | M2_strict_overlap |
| 3 | - | 1,519 | 80% | M3_overwrite_end |
| 4 | - | 1,925 | 100% | M5_empty_returns_none |

## Mutants still surviving

None — every mutant was killed.

## Generated adversarial tests (the changes)

The loop wrote 4 test(s) into this suite:

- [`adversarial_test_01.py`](tests/adversarial_test_01.py)
- [`adversarial_test_02.py`](tests/adversarial_test_02.py)
- [`adversarial_test_03.py`](tests/adversarial_test_03.py)
- [`adversarial_test_04.py`](tests/adversarial_test_04.py)
