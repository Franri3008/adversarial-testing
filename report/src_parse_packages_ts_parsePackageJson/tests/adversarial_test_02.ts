import { parsePackageJson } from "./impl";
import { test, expect } from "vitest";

test("parsePackageJson adversarial", () => {
  // r1_missing_throws_on_empty: must throw when no package.json found
  expect(() => parsePackageJson([])).toThrow();
  expect(() =>
    parsePackageJson([{ path: "src/index.ts", content: "{}" }] as any),
  ).toThrow();

  // r1_first_match_uses_last: first matching package.json should be preferred
  const multi = parsePackageJson([
    {
      path: "package.json",
      content: JSON.stringify({ dependencies: { first: "1.0.0" } }),
    },
    {
      path: "nested/package.json",
      content: JSON.stringify({ dependencies: { second: "2.0.0" } }),
    },
  ] as any);
  expect(multi.dependencies).toEqual([{ name: "first", version: "1.0.0" }]);
  expect(multi.dependencies.find((d) => d.name === "second")).toBeUndefined();

  // r1_empty_string_version_skipped: empty string version must be included
  const result = parsePackageJson([
    {
      path: "package.json",
      content: JSON.stringify({
        dependencies: { empty: "", normal: "1.2.3", numeric: 5 },
        devDependencies: { devEmpty: "", devNormal: "4.5.6" },
      }),
    },
  ] as any);

  expect(result.dependencies).toContainEqual({ name: "empty", version: "" });
  expect(result.dependencies).toContainEqual({
    name: "normal",
    version: "1.2.3",
  });
  expect(result.dependencies.find((d) => d.name === "numeric")).toBeUndefined();
  expect(result.dependencies).toHaveLength(2);

  expect(result.devDependencies).toContainEqual({
    name: "devEmpty",
    version: "",
  });
  expect(result.devDependencies).toContainEqual({
    name: "devNormal",
    version: "4.5.6",
  });
  expect(result.devDependencies).toHaveLength(2);
});