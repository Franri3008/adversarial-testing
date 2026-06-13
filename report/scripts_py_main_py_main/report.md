# Adversarial test-hardening report

## Target

| | |
|---|---|
| repo | `fiberplane/honcpiler` |
| file | `scripts/py/main.py` |
| function | `main` |
| language | python |
| strategy model | `claude-opus-4-8` |
| bulk model | `nvidia/Nemotron-3-Ultra-550b-a55b` |

## Result

![convergence](convergence.png)

- **Baseline (one cold-start test):** 100% kill rate
- **Final (hardened suite):** 89% kill rate over 9 mutants
- **Gain from looping:** +0%
- **Co-evolution:** 1 adversary round(s); 8 distinct bugs caught across waves
  (the adversary kept inventing bugs the suite missed; each wave is a dip-then-recover in the graph above)
- **Stop reason:** `defender_plateau`
- **Tokens spent:** 15,470
- **Cost:** $0.0608

## Run status

| event | phase | iteration | status | detail |
|---|---|---|---|---|
| run_started | harden | - | running | - |
| mutants_generated | harden | - | generated | 5 mutant(s) |
| iteration_completed | harden | 1 | completed | - |
| mutants_generated | harden | 1 | generated | 4 mutant(s) |
| iteration_completed | harden | 2 | completed | - |
| iteration_completed | harden | 3 | completed | - |
| iteration_completed | harden | 4 | completed | - |
| iteration_completed | harden | 5 | completed | - |
| iteration_completed | harden | 6 | completed | - |
| iteration_completed | harden | 7 | completed | - |
| iteration_completed | harden | 8 | completed | - |
| iteration_completed | harden | 9 | completed | - |
| iteration_completed | harden | 10 | completed | - |
| run_finished | harden | - | stopped | defender_plateau |

## Progress per iteration

| iter | tier | cum. tokens | kill rate | killed this round |
|---|---|---|---|---|
| 1 | bulk | 709 | 100% | wrong_string_constant, missing_exclamation, typo_in_name, lowercase_hello, extra_whitespace |
| 2 | bulk | 6,340 | 56% | — |
| 3 | bulk | 9,454 | 89% | r1_extra_branch_on_args, r1_return_value_changed, r1_stderr_instead_of_extra |
| 4 | bulk | 10,851 | 89% | — |
| 5 | bulk | 11,837 | 89% | — |
| 6 | bulk | 12,520 | 89% | — |
| 7 | strategy | 13,159 | 89% | — |
| 8 | strategy | 13,856 | 89% | — |
| 9 | strategy | 14,465 | 89% | — |
| 10 | strategy | 15,470 | 89% | — |

## Mutants generated

| id | status | description |
|---|---|---|
| `extra_whitespace` | killed | Added trailing space inside the printed string |
| `lowercase_hello` | killed | Changed 'Hello' to lowercase 'hello' |
| `missing_exclamation` | killed | Dropped the exclamation mark from the output |
| `r1_env_based_message` | surviving | Reads an environment variable to override the message; absent in tests so default prints, but presence changes behavior |
| `r1_extra_branch_on_args` | surviving | Adds an unused parameter with a default that, when changed, alters output but default keeps test passing... actually changes only when arg passed |
| `r1_return_value_changed` | surviving | Returns a non-None value (1) which tests never check, but breaks callers relying on None |
| `r1_stderr_instead_of_extra` | surviving | Also writes a warning to stderr; capsys.out unaffected so test passes, but stderr behavior differs |
| `typo_in_name` | killed | Introduced a typo in 'honcpiler' |
| `wrong_string_constant` | killed | Changed printed string to a different message |

<details>
<summary>extra_whitespace source</summary>

```python
def main():
    print("Hello from honcpiler! ")


if __name__ == "__main__":
    main()
```

</details>

<details>
<summary>lowercase_hello source</summary>

```python
def main():
    print("hello from honcpiler!")


if __name__ == "__main__":
    main()
```

</details>

<details>
<summary>missing_exclamation source</summary>

```python
def main():
    print("Hello from honcpiler")


if __name__ == "__main__":
    main()
```

</details>

<details>
<summary>r1_env_based_message source</summary>

```python
import os


def main():
    print(os.environ.get("HONC_MSG", "Hello from honcpiler!"))


if __name__ == "__main__":
    main()
```

</details>

<details>
<summary>r1_extra_branch_on_args source</summary>

```python
def main(greeting="Hello from honcpiler!"):
    print(greeting)


if __name__ == "__main__":
    main()
```

</details>

<details>
<summary>r1_return_value_changed source</summary>

```python
def main():
    print("Hello from honcpiler!")
    return 1


if __name__ == "__main__":
    main()
```

</details>

<details>
<summary>r1_stderr_instead_of_extra source</summary>

```python
import sys


def main():
    print("Hello from honcpiler!")
    sys.stderr.write("warning: deprecated\n")


if __name__ == "__main__":
    main()
```

</details>

<details>
<summary>typo_in_name source</summary>

```python
def main():
    print("Hello from honcpilre!")


if __name__ == "__main__":
    main()
```

</details>

<details>
<summary>wrong_string_constant source</summary>

```python
def main():
    print("Goodbye from honcpiler!")


if __name__ == "__main__":
    main()
```

</details>

## Fixes accepted

No accepted fixes were recorded.

## Fixes rejected

No rejected fixes were recorded.

## Generated adversarial tests (the changes)

The loop wrote 2 test(s) into this suite:

- [`adversarial_test_01.py`](tests/adversarial_test_01.py)
- [`adversarial_test_02.py`](tests/adversarial_test_02.py)
