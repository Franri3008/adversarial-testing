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

- **Baseline (one cold-start test):** 0% kill rate
- **Final (hardened suite):** 88% kill rate over 8 mutants
- **Gain from looping:** +88%
- **Co-evolution:** 1 adversary round(s); 7 distinct bugs caught across waves
  (the adversary kept inventing bugs the suite missed; each wave is a dip-then-recover in the graph above)
- **Stop reason:** `defender_plateau`
- **Tokens spent:** 49,594
- **Cost:** $0.2219

## Run status

| event | phase | iteration | status | detail |
|---|---|---|---|---|
| run_started | harden | - | running | - |
| mutants_generated | harden | - | generated | 5 mutant(s) |
| iteration_completed | harden | 1 | completed | - |
| iteration_completed | harden | 2 | completed | - |
| iteration_completed | harden | 3 | completed | - |
| iteration_completed | harden | 4 | completed | - |
| iteration_completed | harden | 5 | completed | - |
| iteration_completed | harden | 6 | completed | - |
| iteration_completed | harden | 7 | completed | - |
| iteration_completed | harden | 8 | completed | - |
| mutants_generated | harden | 8 | generated | 3 mutant(s) |
| iteration_completed | harden | 9 | completed | - |
| iteration_completed | harden | 10 | completed | - |
| iteration_completed | harden | 11 | completed | - |
| iteration_completed | harden | 12 | completed | - |
| iteration_completed | harden | 13 | completed | - |
| iteration_completed | harden | 14 | completed | - |
| iteration_completed | harden | 15 | completed | - |
| iteration_completed | harden | 16 | completed | - |
| run_finished | harden | - | stopped | defender_plateau |

## Progress per iteration

| iter | tier | cum. tokens | kill rate | killed this round |
|---|---|---|---|---|
| 1 | bulk | 4,676 | 40% | swap_dep_targets, wrong_not_found_default |
| 2 | bulk | 6,527 | 40% | — |
| 3 | bulk | 10,536 | 60% | flip_version_type_check |
| 4 | bulk | 12,431 | 60% | — |
| 5 | bulk | 13,942 | 60% | — |
| 6 | bulk | 15,509 | 60% | — |
| 7 | strategy | 17,079 | 80% | drop_devdeps_guard |
| 8 | strategy | 18,641 | 100% | endswith_to_includes |
| 9 | bulk | 31,412 | 62% | — |
| 10 | bulk | 32,842 | 62% | — |
| 11 | bulk | 37,715 | 62% | — |
| 12 | bulk | 42,588 | 62% | — |
| 13 | strategy | 44,402 | 88% | r1_trim_version_silently, r1_skip_empty_string_versions |
| 14 | strategy | 46,094 | 88% | — |
| 15 | strategy | 48,098 | 88% | — |
| 16 | strategy | 49,594 | 88% | — |

## Mutants generated

| id | status | description |
|---|---|---|
| `drop_devdeps_guard` | killed | Dropped object type guard on devDependencies causing crash on non-object |
| `endswith_to_includes` | killed | Uses includes instead of endsWith for package.json path matching |
| `flip_version_type_check` | killed | Flipped type check pushes non-string dependency versions |
| `r1_deps_type_check_includes_arrays` | surviving | Uses Array.isArray rejection wrong way - actually drops the object check so an array of versions could be entered (but tests only use object/missing deps) |
| `r1_skip_empty_string_versions` | surviving | Adds an extra condition that skips empty-string versions, dropping deps with version "" (not tested) |
| `r1_trim_version_silently` | surviving | Trims whitespace from version strings, altering output for versions with leading/trailing spaces (not covered by tests) |
| `swap_dep_targets` | killed | devDependencies entries pushed into dependencies array |
| `wrong_not_found_default` | killed | Returns empty result instead of throwing when package.json missing |

<details>
<summary>drop_devdeps_guard source</summary>

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
      packageJson.dependencies &&
      typeof packageJson.dependencies === "object"
    ) {
      for (const [name, version] of Object.entries(packageJson.dependencies)) {
        if (typeof version === "string") {
          dependencies.push({ name, version });
        }
      }
    }

    // Parse devDependencies
    if (packageJson.devDependencies) {
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

<details>
<summary>endswith_to_includes source</summary>

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
      file.path.includes("/package.json"),
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
      packageJson.dependencies &&
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
      packageJson.devDependencies &&
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

<details>
<summary>flip_version_type_check source</summary>

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
      packageJson.dependencies &&
      typeof packageJson.dependencies === "object"
    ) {
      for (const [name, version] of Object.entries(packageJson.dependencies)) {
        if (typeof version !== "string") {
          dependencies.push({ name, version });
        }
      }
    }

    // Parse devDependencies
    if (
      packageJson.devDependencies &&
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

<details>
<summary>r1_deps_type_check_includes_arrays source</summary>

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

    if (
      packageJson.dependencies != null &&
      typeof packageJson.dependencies !== "string"
    ) {
      for (const [name, version] of Object.entries(packageJson.dependencies)) {
        if (typeof version === "string") {
          dependencies.push({ name, version });
        }
      }
    }

    if (
      packageJson.devDependencies &&
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

<details>
<summary>r1_skip_empty_string_versions source</summary>

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

    if (
      packageJson.dependencies &&
      typeof packageJson.dependencies === "object"
    ) {
      for (const [name, version] of Object.entries(packageJson.dependencies)) {
        if (typeof version === "string" && version.length > 0) {
          dependencies.push({ name, version });
        }
      }
    }

    if (
      packageJson.devDependencies &&
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

<details>
<summary>r1_trim_version_silently source</summary>

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

    if (
      packageJson.dependencies &&
      typeof packageJson.dependencies === "object"
    ) {
      for (const [name, version] of Object.entries(packageJson.dependencies)) {
        if (typeof version === "string") {
          dependencies.push({ name, version: version.trim() });
        }
      }
    }

    if (
      packageJson.devDependencies &&
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

<details>
<summary>swap_dep_targets source</summary>

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
      packageJson.dependencies &&
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
      packageJson.devDependencies &&
      typeof packageJson.devDependencies === "object"
    ) {
      for (const [name, version] of Object.entries(
        packageJson.devDependencies,
      )) {
        if (typeof version === "string") {
          dependencies.push({ name, version });
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

<details>
<summary>wrong_not_found_default source</summary>

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
    return { dependencies: [], devDependencies: [] };
  }

  try {
    const packageJson = JSON.parse(packageJsonFile.content);

    const dependencies: PackageDependency[] = [];
    const devDependencies: PackageDependency[] = [];

    // Parse dependencies
    if (
      packageJson.dependencies &&
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
      packageJson.devDependencies &&
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

The loop wrote 5 test(s) into this suite:

- [`adversarial_test_01.ts`](tests/adversarial_test_01.ts)
- [`adversarial_test_02.ts`](tests/adversarial_test_02.ts)
- [`adversarial_test_03.ts`](tests/adversarial_test_03.ts)
- [`adversarial_test_04.ts`](tests/adversarial_test_04.ts)
- [`adversarial_test_05.ts`](tests/adversarial_test_05.ts)
