import { parsePackageJson } from "./impl";
import { test, expect } from "vitest";

test("parsePackageJson handles various edge cases and bugs", () => {
  // 1. endswith_wrong_suffix: should not match "my-package.json"
  const inputWithWrongSuffix = [
    { path: "my-package.json", content: '{"dependencies": {"foo": "1.0.0"}}' },
  ];
  expect(() => parsePackageJson(inputWithWrongSuffix)).toThrow("no package.json found in input files");

  // 2. dropped_guard_no_throw: missing package.json should throw
  const inputWithoutPackageJson = [
    { path: "other.json", content: "{}" },
  ];
  expect(() => parsePackageJson(inputWithoutPackageJson)).toThrow("no package.json found in input files");

  // 3. version_type_check_flipped: only string versions should be included
  const inputWithMixedVersions = [
    {
      path: "package.json",
      content: JSON.stringify({
        dependencies: {
          stringDep: "1.0.0",
          numberDep: 2,
          objectDep: {},
        },
        devDependencies: {
          stringDev: "2.0.0",
          boolDev: true,
        },
      }),
    },
  ];
  const resultMixed = parsePackageJson(inputWithMixedVersions);
  expect(resultMixed.dependencies).toEqual([{ name: "stringDep", version: "1.0.0" }]);
  expect(resultMixed.devDependencies).toEqual([{ name: "stringDev", version: "2.0.0" }]);

  // 4. devdeps_use_dependencies: devDependencies should come from devDependencies field, not dependencies
  const inputDevDeps = [
    {
      path: "package.json",
      content: JSON.stringify({
        dependencies: {
          dep1: "1.0.0",
        },
        devDependencies: {
          dev1: "2.0.0",
        },
      }),
    },
  ];
  const resultDevDeps = parsePackageJson(inputDevDeps);
  expect(resultDevDeps.dependencies).toEqual([{ name: "dep1", version: "1.0.0" }]);
  expect(resultDevDeps.devDependencies).toEqual([{ name: "dev1", version: "2.0.0" }]);

  // 5. deps_or_instead_of_and: missing dependencies should not crash, return empty array
  const inputMissingDeps = [
    {
      path: "package.json",
      content: JSON.stringify({
        devDependencies: {
          devOnly: "1.0.0",
        },
      }),
    },
  ];
  const resultMissingDeps = parsePackageJson(inputMissingDeps);
  expect(resultMissingDeps.dependencies).toEqual([]);
  expect(resultMissingDeps.devDependencies).toEqual([{ name: "devOnly", version: "1.0.0" }]);

  // Also test missing devDependencies
  const inputMissingDevDeps = [
    {
      path: "package.json",
      content: JSON.stringify({
        dependencies: {
          depOnly: "1.0.0",
        },
      }),
    },
  ];
  const resultMissingDevDeps = parsePackageJson(inputMissingDevDeps);
  expect(resultMissingDevDeps.dependencies).toEqual([{ name: "depOnly", version: "1.0.0" }]);
  expect(resultMissingDevDeps.devDependencies).toEqual([]);
});