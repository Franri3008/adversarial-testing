import { parsePackageJson } from "./impl";
import { test, expect } from "vitest";

test("parsePackageJson handles edge cases and catches target bugs", () => {
  // Bug: endswith_to_includes - should not match package.json.backup or package.json.old
  const inputWithSimilarNames = [
    { path: "package.json", content: JSON.stringify({ dependencies: { "main": "1.0.0" } }) },
    { path: "package.json.backup", content: JSON.stringify({ dependencies: { "backup": "2.0.0" } }) },
    { path: "src/package.json.old", content: JSON.stringify({ dependencies: { "old": "3.0.0" } }) },
  ];
  const result1 = parsePackageJson(inputWithSimilarNames);
  expect(result1.dependencies).toEqual([{ name: "main", version: "1.0.0" }]);
  expect(result1.devDependencies).toEqual([]);

  // Bug: flip_version_type_check - should only include string versions
  const inputWithNonStringVersions = [
    { path: "package.json", content: JSON.stringify({
      dependencies: {
        "string-dep": "1.0.0",
        "number-dep": 2,
        "object-dep": { version: "3.0.0" },
        "null-dep": null,
        "array-dep": ["1.0.0"]
      }
    })},
  ];
  const result2 = parsePackageJson(inputWithNonStringVersions);
  expect(result2.dependencies).toEqual([{ name: "string-dep", version: "1.0.0" }]);

  // Bug: drop_devdeps_guard - should not crash on null devDependencies
  const inputWithNullDevDeps = [
    { path: "package.json", content: JSON.stringify({
      dependencies: { "dep1": "1.0.0" },
      devDependencies: null
    })},
  ];
  const result3 = parsePackageJson(inputWithNullDevDeps);
  expect(result3.dependencies).toEqual([{ name: "dep1", version: "1.0.0" }]);
  expect(result3.devDependencies).toEqual([]);

  // Bug: swap_dep_targets - should keep dependencies and devDependencies separate
  const inputWithBoth = [
    { path: "package.json", content: JSON.stringify({
      dependencies: { "prod": "1.0.0" },
      devDependencies: { "dev": "2.0.0" }
    })},
  ];
  const result4 = parsePackageJson(inputWithBoth);
  expect(result4.dependencies).toEqual([{ name: "prod", version: "1.0.0" }]);
  expect(result4.devDependencies).toEqual([{ name: "dev", version: "2.0.0" }]);

  // Bug: wrong_not_found_default - should throw when package.json missing
  const inputWithoutPackageJson = [
    { path: "tsconfig.json", content: "{}" },
    { path: "src/index.ts", content: "console.log('hi')" },
  ];
  expect(() => parsePackageJson(inputWithoutPackageJson)).toThrow("no package.json found in input files");
});