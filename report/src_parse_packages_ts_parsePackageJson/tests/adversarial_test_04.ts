import { test, expect } from "vitest";
import { parsePackageJson } from "./impl";

test("only matches package.json suffix, not substring", () => {
  // This file path CONTAINS "package.json" but does NOT end with it.
  // With endsWith: not matched -> no package.json found -> throws.
  // With includes: incorrectly matched -> parses dependencies.
  const input = [
    {
      path: "src/package.json.bak",
      content: JSON.stringify({
        dependencies: { lodash: "1.0.0" },
        devDependencies: { vitest: "2.0.0" },
      }),
    },
  ];

  expect(() => parsePackageJson(input)).toThrow();

  // Sanity check: a correct suffix path is parsed properly.
  const valid = [
    {
      path: "nested/dir/package.json",
      content: JSON.stringify({
        dependencies: { lodash: "1.0.0" },
        devDependencies: { vitest: "2.0.0" },
      }),
    },
  ];

  const result = parsePackageJson(valid);
  expect(result.dependencies).toEqual([{ name: "lodash", version: "1.0.0" }]);
  expect(result.devDependencies).toEqual([{ name: "vitest", version: "2.0.0" }]);
});