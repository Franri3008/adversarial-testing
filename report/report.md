# Adversarial test-hardening report

## Target

| | |
|---|---|
| repo | `fiberplane/honcpiler` |
| file | `src/parse-packages.ts` |
| function | `parsePackageJson` |
| language | typescript |
| strategy model | `claude-opus-4-8` |
| bulk model | `nvidia/Nemotron-3-Ultra-550b-a55b` |

## Result

![convergence](convergence.png)

- **Baseline (one cold-start test):** 80% kill rate
- **Final (hardened suite):** 88% kill rate over 8 mutants
- **Gain from looping:** +7%
- **Co-evolution:** 1 adversary round(s); 7 distinct bugs caught across waves
  (the adversary kept inventing bugs the suite missed; each wave is a dip-then-recover in the graph above)
- **Stop reason:** `-`
- **Tokens spent:** 44,672

## Run status

| event | phase | iteration | status | detail |
|---|---|---|---|---|

## Progress per iteration

| iter | tier | cum. tokens | kill rate | killed this round |
|---|---|---|---|---|
| 1 | - | 2,150 | 80% | endswith_wrong_suffix, dropped_guard_no_throw, version_type_check_flipped, devdeps_use_dependencies |
| 2 | - | 5,411 | 100% | deps_or_instead_of_and |
| 3 | - | 18,387 | 62% | — |
| 4 | - | 23,149 | 62% | — |
| 5 | - | 27,911 | 62% | — |
| 6 | - | 32,673 | 62% | — |
| 7 | - | 34,671 | 62% | — |
| 8 | - | 36,520 | 75% | r1_empty_string_version_excluded |
| 9 | - | 38,821 | 88% | r1_find_last_package_json |
| 10 | - | 40,641 | 88% | — |
| 11 | - | 42,470 | 88% | — |
| 12 | - | 44,672 | 88% | — |

## Mutants generated

| id | status | description |
|---|---|---|
| `r1_array_typeof_object_accepts_array` | surviving | Uses Array.isArray-negation-free object check that allows dependencies as an array; arrays pass the object check and Object.entries yields indices, untested by suite. |

<details>
<summary>r1_array_typeof_object_accepts_array source</summary>

```ts
import type { InputFiles } from "./typescript-compile";

export type PackageDependency = {
  name: string;
  version: string;
};

export type ParsedDependencies = {
  dependencies: PackageDependency[];
  devDependencies: PackageDependency[];
};

/**
 * Parses package.json from InputFiles array and extracts all dependencies and devDependencies
 * @param input Array of input files
 * @returns Object containing parsed dependencies and devDependencies
 */
export function parsePackageJson(input: InputFiles[]): ParsedDependencies {
  // Find package.json file in the input array
  const packageJsonFile = input.find(
    (file) =>
      file.path === "package.json" ||
      file.path === "/package.json" ||
      file.path.endsWith("/package.json"),
  );

  if (!packageJsonFile) {
    throw new Error("no package.json found in input files");
  }

  try {
    const packageJson = JSON.parse(packageJsonFile.content);

    const dependencies: PackageDependency[] = [];
    const devDependencies: PackageDependency[] = [];

    // Parse dependencies
    if (
      packageJson.dependencies != null &&
      typeof packageJson.dependencies === "object"
    ) {
      for (const [name, version] of Object.entries(packageJson.dependencies)) {
        if (typeof version === "string") {
          dependencies.push({ name, version });
        }
      }
    }

    // Parse devDependencies
    if (
      packageJson.devDependencies != null &&
      typeof packageJson.devDependencies === "object"
    ) {
      for (const [name, version] of Object.entries(
        packageJson.devDependencies,
      )) {
        if (typeof version === "string") {
          devDependencies.push({ name, version });
        }
      }
    }

    return {
      dependencies,
      devDependencies,
    };
  } catch (error) {
    console.error("[parsePackageJson] Failed to parse package.json:", error);
    throw error;
  }
}
```

</details>

## Fixes accepted

No accepted fixes were recorded.

## Fixes rejected

No rejected fixes were recorded.

## Generated adversarial tests (the changes)

The loop wrote 4 test(s) into this suite:

- [`adversarial_test_01.ts`](tests/adversarial_test_01.ts)
- [`adversarial_test_02.ts`](tests/adversarial_test_02.ts)
- [`adversarial_test_03.ts`](tests/adversarial_test_03.ts)
- [`adversarial_test_04.ts`](tests/adversarial_test_04.ts)
