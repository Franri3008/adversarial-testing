# Adversarial test-hardening report

## Target

| | |
|---|---|
| repo | `fiberplane/honcpiler` |
| file | `src/vfs/utils/parse-package-with-version.ts` |
| function | `parsePackageWithVersion` |
| language | typescript |
| strategy model | `claude-opus-4-8` |
| bulk model | `nvidia/Nemotron-3-Ultra-550b-a55b` |

## Result

![convergence](convergence.png)

- **Baseline (one cold-start test):** 100% kill rate
- **Final (hardened suite):** 86% kill rate over 7 mutants
- **Gain from looping:** +0%
- **Co-evolution:** 1 adversary round(s); 6 distinct bugs caught across waves
  (the adversary kept inventing bugs the suite missed; each wave is a dip-then-recover in the graph above)
- **Stop reason:** `defender_plateau`
- **Tokens spent:** 24,837
- **Cost:** $0.1497

## Run status

| event | phase | iteration | status | detail |
|---|---|---|---|---|
| run_started | harden | - | running | - |
| mutants_generated | harden | - | generated | 5 mutant(s) |
| iteration_completed | harden | 1 | completed | - |
| iteration_completed | harden | 2 | completed | - |
| mutants_generated | harden | 2 | generated | 2 mutant(s) |
| iteration_completed | harden | 3 | completed | - |
| iteration_completed | harden | 4 | completed | - |
| iteration_completed | harden | 5 | completed | - |
| iteration_completed | harden | 6 | completed | - |
| iteration_completed | harden | 7 | completed | - |
| iteration_completed | harden | 8 | completed | - |
| iteration_completed | harden | 9 | completed | - |
| iteration_completed | harden | 10 | completed | - |
| iteration_completed | harden | 11 | completed | - |
| run_finished | harden | - | stopped | defender_plateau |

## Progress per iteration

| iter | tier | cum. tokens | kill rate | killed this round |
|---|---|---|---|---|
| 1 | bulk | 2,214 | 80% | scope_default_version_changed, version_off_by_one_includes_at, scope_off_by_one_excludes_slash, regular_no_at_guard_flipped |
| 2 | bulk | 3,299 | 100% | scope_uses_lastindexof |
| 3 | bulk | 12,790 | 71% | — |
| 4 | bulk | 15,926 | 86% | r1_scope_no_slash_default_empty_version |
| 5 | bulk | 17,021 | 86% | — |
| 6 | bulk | 18,109 | 86% | — |
| 7 | bulk | 19,199 | 86% | — |
| 8 | strategy | 20,589 | 86% | — |
| 9 | strategy | 22,036 | 86% | — |
| 10 | strategy | 23,431 | 86% | — |
| 11 | strategy | 24,837 | 86% | — |

## Mutants generated

| id | status | description |
|---|---|---|
| `r1_regular_version_empty_when_trailing_at` | surviving | Regular package ending with '@' yields empty version, but uses substring with wrong index handling for empty afterScope cases |
| `r1_scope_no_slash_default_empty_version` | surviving | Invalid scoped package without slash returns empty version instead of 'latest' |
| `regular_no_at_guard_flipped` | killed | Regular package guard flipped to firstAtIndex !== -1, mishandling no-version case |
| `scope_default_version_changed` | killed | Scoped package without version returns 'unknown' instead of 'latest' |
| `scope_off_by_one_excludes_slash` | killed | Scope substring uses scopeEndIndex instead of +1, dropping the '/' separator |
| `scope_uses_lastindexof` | killed | Scoped version separator uses lastIndexOf('@') instead of indexOf, splitting on wrong '@' |
| `version_off_by_one_includes_at` | killed | Version substring starts at versionAtIndex instead of +1, keeping the '@' |

<details>
<summary>r1_regular_version_empty_when_trailing_at source</summary>

```ts
export interface ParsedPackage {
  name: string;
  version: string;
}

export function parsePackageWithVersion(
  packageWithVersion: string,
): ParsedPackage {
  // Handle scoped packages like @types/node@18.0.0
  if (packageWithVersion.startsWith("@")) {
    const scopeEndIndex = packageWithVersion.indexOf("/");
    if (scopeEndIndex === -1) {
      return { name: packageWithVersion, version: "latest" };
    }

    const afterScope = packageWithVersion.substring(scopeEndIndex + 1);
    const versionAtIndex = afterScope.indexOf("@");

    if (versionAtIndex === -1) {
      return { name: packageWithVersion, version: "latest" };
    }

    const scope = packageWithVersion.substring(0, scopeEndIndex + 1);
    const nameAfterScope = afterScope.substring(0, versionAtIndex);
    const version = afterScope.substring(versionAtIndex + 1);

    return { name: scope + nameAfterScope, version };
  }

  const firstAtIndex = packageWithVersion.indexOf("@");
  if (firstAtIndex <= 0) {
    return { name: packageWithVersion, version: "latest" };
  }

  const name = packageWithVersion.substring(0, firstAtIndex);
  const version = packageWithVersion.substring(firstAtIndex + 1);

  return { name, version };
}
```

</details>

<details>
<summary>r1_scope_no_slash_default_empty_version source</summary>

```ts
export interface ParsedPackage {
  name: string;
  version: string;
}

export function parsePackageWithVersion(
  packageWithVersion: string,
): ParsedPackage {
  // Handle scoped packages like @types/node@18.0.0
  if (packageWithVersion.startsWith("@")) {
    const scopeEndIndex = packageWithVersion.indexOf("/");
    if (scopeEndIndex === -1) {
      return { name: packageWithVersion, version: "" };
    }

    const afterScope = packageWithVersion.substring(scopeEndIndex + 1);
    const versionAtIndex = afterScope.indexOf("@");

    if (versionAtIndex === -1) {
      return { name: packageWithVersion, version: "latest" };
    }

    const scope = packageWithVersion.substring(0, scopeEndIndex + 1);
    const nameAfterScope = afterScope.substring(0, versionAtIndex);
    const version = afterScope.substring(versionAtIndex + 1);

    return { name: scope + nameAfterScope, version };
  }

  const firstAtIndex = packageWithVersion.indexOf("@");
  if (firstAtIndex === -1) {
    return { name: packageWithVersion, version: "latest" };
  }

  const name = packageWithVersion.substring(0, firstAtIndex);
  const version = packageWithVersion.substring(firstAtIndex + 1);

  return { name, version };
}
```

</details>

<details>
<summary>regular_no_at_guard_flipped source</summary>

```ts
export interface ParsedPackage {
  name: string;
  version: string;
}

export function parsePackageWithVersion(
  packageWithVersion: string,
): ParsedPackage {
  if (packageWithVersion.startsWith("@")) {
    const scopeEndIndex = packageWithVersion.indexOf("/");
    if (scopeEndIndex === -1) {
      return { name: packageWithVersion, version: "latest" };
    }

    const afterScope = packageWithVersion.substring(scopeEndIndex + 1);
    const versionAtIndex = afterScope.indexOf("@");

    if (versionAtIndex === -1) {
      return { name: packageWithVersion, version: "latest" };
    }

    const scope = packageWithVersion.substring(0, scopeEndIndex + 1);
    const nameAfterScope = afterScope.substring(0, versionAtIndex);
    const version = afterScope.substring(versionAtIndex + 1);

    return { name: scope + nameAfterScope, version };
  }

  const firstAtIndex = packageWithVersion.indexOf("@");
  if (firstAtIndex !== -1) {
    return { name: packageWithVersion, version: "latest" };
  }

  const name = packageWithVersion.substring(0, firstAtIndex);
  const version = packageWithVersion.substring(firstAtIndex + 1);

  return { name, version };
}
```

</details>

<details>
<summary>scope_default_version_changed source</summary>

```ts
export interface ParsedPackage {
  name: string;
  version: string;
}

export function parsePackageWithVersion(
  packageWithVersion: string,
): ParsedPackage {
  if (packageWithVersion.startsWith("@")) {
    const scopeEndIndex = packageWithVersion.indexOf("/");
    if (scopeEndIndex === -1) {
      return { name: packageWithVersion, version: "latest" };
    }

    const afterScope = packageWithVersion.substring(scopeEndIndex + 1);
    const versionAtIndex = afterScope.indexOf("@");

    if (versionAtIndex === -1) {
      return { name: packageWithVersion, version: "unknown" };
    }

    const scope = packageWithVersion.substring(0, scopeEndIndex + 1);
    const nameAfterScope = afterScope.substring(0, versionAtIndex);
    const version = afterScope.substring(versionAtIndex + 1);

    return { name: scope + nameAfterScope, version };
  }

  const firstAtIndex = packageWithVersion.indexOf("@");
  if (firstAtIndex === -1) {
    return { name: packageWithVersion, version: "latest" };
  }

  const name = packageWithVersion.substring(0, firstAtIndex);
  const version = packageWithVersion.substring(firstAtIndex + 1);

  return { name, version };
}
```

</details>

<details>
<summary>scope_off_by_one_excludes_slash source</summary>

```ts
export interface ParsedPackage {
  name: string;
  version: string;
}

export function parsePackageWithVersion(
  packageWithVersion: string,
): ParsedPackage {
  if (packageWithVersion.startsWith("@")) {
    const scopeEndIndex = packageWithVersion.indexOf("/");
    if (scopeEndIndex === -1) {
      return { name: packageWithVersion, version: "latest" };
    }

    const afterScope = packageWithVersion.substring(scopeEndIndex + 1);
    const versionAtIndex = afterScope.indexOf("@");

    if (versionAtIndex === -1) {
      return { name: packageWithVersion, version: "latest" };
    }

    const scope = packageWithVersion.substring(0, scopeEndIndex);
    const nameAfterScope = afterScope.substring(0, versionAtIndex);
    const version = afterScope.substring(versionAtIndex + 1);

    return { name: scope + nameAfterScope, version };
  }

  const firstAtIndex = packageWithVersion.indexOf("@");
  if (firstAtIndex === -1) {
    return { name: packageWithVersion, version: "latest" };
  }

  const name = packageWithVersion.substring(0, firstAtIndex);
  const version = packageWithVersion.substring(firstAtIndex + 1);

  return { name, version };
}
```

</details>

<details>
<summary>scope_uses_lastindexof source</summary>

```ts
export interface ParsedPackage {
  name: string;
  version: string;
}

export function parsePackageWithVersion(
  packageWithVersion: string,
): ParsedPackage {
  if (packageWithVersion.startsWith("@")) {
    const scopeEndIndex = packageWithVersion.indexOf("/");
    if (scopeEndIndex === -1) {
      return { name: packageWithVersion, version: "latest" };
    }

    const afterScope = packageWithVersion.substring(scopeEndIndex + 1);
    const versionAtIndex = afterScope.lastIndexOf("@");

    if (versionAtIndex === -1) {
      return { name: packageWithVersion, version: "latest" };
    }

    const scope = packageWithVersion.substring(0, scopeEndIndex + 1);
    const nameAfterScope = afterScope.substring(0, versionAtIndex);
    const version = afterScope.substring(versionAtIndex + 1);

    return { name: scope + nameAfterScope, version };
  }

  const firstAtIndex = packageWithVersion.indexOf("@");
  if (firstAtIndex === -1) {
    return { name: packageWithVersion, version: "latest" };
  }

  const name = packageWithVersion.substring(0, firstAtIndex);
  const version = packageWithVersion.substring(firstAtIndex + 1);

  return { name, version };
}
```

</details>

<details>
<summary>version_off_by_one_includes_at source</summary>

```ts
export interface ParsedPackage {
  name: string;
  version: string;
}

export function parsePackageWithVersion(
  packageWithVersion: string,
): ParsedPackage {
  if (packageWithVersion.startsWith("@")) {
    const scopeEndIndex = packageWithVersion.indexOf("/");
    if (scopeEndIndex === -1) {
      return { name: packageWithVersion, version: "latest" };
    }

    const afterScope = packageWithVersion.substring(scopeEndIndex + 1);
    const versionAtIndex = afterScope.indexOf("@");

    if (versionAtIndex === -1) {
      return { name: packageWithVersion, version: "latest" };
    }

    const scope = packageWithVersion.substring(0, scopeEndIndex + 1);
    const nameAfterScope = afterScope.substring(0, versionAtIndex);
    const version = afterScope.substring(versionAtIndex);

    return { name: scope + nameAfterScope, version };
  }

  const firstAtIndex = packageWithVersion.indexOf("@");
  if (firstAtIndex === -1) {
    return { name: packageWithVersion, version: "latest" };
  }

  const name = packageWithVersion.substring(0, firstAtIndex);
  const version = packageWithVersion.substring(firstAtIndex + 1);

  return { name, version };
}
```

</details>

## Fixes accepted

No accepted fixes were recorded.

## Fixes rejected

No rejected fixes were recorded.

## Generated adversarial tests (the changes)

The loop wrote 3 test(s) into this suite:

- [`adversarial_test_01.ts`](tests/adversarial_test_01.ts)
- [`adversarial_test_02.ts`](tests/adversarial_test_02.ts)
- [`adversarial_test_03.ts`](tests/adversarial_test_03.ts)
