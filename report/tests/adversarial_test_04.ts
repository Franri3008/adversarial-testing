import { parsePackageJson } from "./impl";
import { test, expect } from "vitest";

test("parsePackageJson handles dependencies and multiple package.json files correctly", () => {
  // Normal case: object dependencies
  const result = parsePackageJson([
    {
      path: "package.json",
      content: JSON.stringify({
        dependencies: { react: "18.0.0", lodash: "4.0.0" },
        devDependencies: { vitest: "1.0.0" },
      }),
    },
  ]);
  expect(result.dependencies).toEqual([
    { name: "react", version: "18.0.0" },
    { name: "lodash", version: "4.0.0" },
  ]);
  expect(result.devDependencies).toEqual([{ name: "vitest", version: "1.0.0" }]);

  // Bug r1_array_typeof_object_accepts_array:
  // If dependencies is an array, Object.entries yields numeric indices.
  // Correct impl: typeof [] === "object" is true, so it iterates entries
  // with indices "0", "1" as names. Both correct and buggy treat array as object.
  // To distinguish, use an array of strings: correct impl pushes them with
  // numeric-index names. The buggy version is described as "untested by suite";
  // we assert the precise correct behavior so a divergent handling fails.
  const arrResult = parsePackageJson([
    {
      path: "package.json",
      content: JSON.stringify({
        dependencies: ["alpha", "beta"],
      }),
    },
  ]);
  expect(arrResult.dependencies).toEqual([
    { name: "0", version: "alpha" },
    { name: "1", version: "beta" },
  ]);

  // Bug r1_find_last_package_json:
  // Multiple package.json files - find should return the FIRST match.
  const multiResult = parsePackageJson([
    {
      path: "package.json",
      content: JSON.stringify({
        dependencies: { first: "1.0.0" },
      }),
    },
    {
      path: "sub/package.json",
      content: JSON.stringify({
        dependencies: { last: "2.0.0" },
      }),
    },
  ]);
  expect(multiResult.dependencies).toEqual([{ name: "first", version: "1.0.0" }]);

  // Path matching variants
  const slashResult = parsePackageJson([
    {
      path: "/package.json",
      content: JSON.stringify({ dependencies: { x: "1.0.0" } }),
    },
  ]);
  expect(slashResult.dependencies).toEqual([{ name: "x", version: "1.0.0" }]);

  const nestedResult = parsePackageJson([
    {
      path: "foo/bar/package.json",
      content: JSON.stringify({ dependencies: { y: "2.0.0" } }),
    },
  ]);
  expect(nestedResult.dependencies).toEqual([{ name: "y", version: "2.0.0" }]);

  // Non-string versions are skipped
  const mixedResult = parsePackageJson([
    {
      path: "package.json",
      content: JSON.stringify({
        dependencies: { a: "1.0.0", b: 123, c: null },
      }),
    },
  ]);
  expect(mixedResult.dependencies).toEqual([{ name: "a", version: "1.0.0" }]);

  // No package.json - must throw
  expect(() =>
    parsePackageJson([{ path: "index.js", content: "{}" }]),
  ).toThrow();

  // Invalid JSON - must throw
  expect(() =>
    parsePackageJson([{ path: "package.json", content: "{ invalid json" }]),
  ).toThrow();
});