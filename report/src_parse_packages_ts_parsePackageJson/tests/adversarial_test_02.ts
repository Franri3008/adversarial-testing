import { parsePackageJson } from "./impl";
import { test, expect } from "vitest";

test("parsePackageJson handles path matching, version type validation, and devDependencies type guard", () => {
  // Bug 1: endswith_to_includes - should not match "my-package.json"
  const inputPathMatch = [
    { path: "my-package.json", content: '{"dependencies": {"wrong": "1.0.0"}}' },
    { path: "package.json", content: '{"dependencies": {"correct": "2.0.0"}}' },
  ];
  const resultPath = parsePackageJson(inputPathMatch);
  expect(resultPath.dependencies).toEqual([{ name: "correct", version: "2.0.0" }]);
  expect(resultPath.devDependencies).toEqual([]);

  // Bug 2: flip_version_type_check - non-string versions should be skipped
  const inputNonStringVersion = [
    {
      path: "package.json",
      content: JSON.stringify({
        dependencies: {
          "valid-string": "1.0.0",
          "invalid-number": 2,
          "invalid-object": { major: 1 },
          "invalid-boolean": true,
        },
      }),
    },
  ];
  const resultVersion = parsePackageJson(inputNonStringVersion);
  expect(resultVersion.dependencies).toEqual([{ name: "valid-string", version: "1.0.0" }]);

  // Bug 3: drop_devdeps_guard - devDependencies as truthy non-object (boolean) should not crash
  const inputInvalidDevDeps = [
    {
      path: "package.json",
      content: JSON.stringify({
        dependencies: { "prod-dep": "1.0.0" },
        devDependencies: true,
      }),
    },
  ];
  const resultDevDeps = parsePackageJson(inputInvalidDevDeps);
  expect(resultDevDeps.dependencies).toEqual([{ name: "prod-dep", version: "1.0.0" }]);
  expect(resultDevDeps.devDependencies).toEqual([]);

  // Missing package.json should throw
  expect(() => parsePackageJson([{ path: "other.json", content: "{}" }])).toThrow(
    "no package.json found",
  );
});