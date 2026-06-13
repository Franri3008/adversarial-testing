import { parsePackageJson } from "./impl";
import { test, expect } from "vitest";

test("parsePackageJson adversarial", () => {
  const input = [
    {
      path: "package.json",
      content: JSON.stringify({
        dependencies: {
          react: "^18.0.0",
          empty: "",
        },
        devDependencies: {
          vitest: "^1.0.0",
        },
      }),
    },
  ];

  const result = parsePackageJson(input);

  // r1_empty_string_version_excluded: empty-string version must be kept
  expect(result.dependencies).toHaveLength(2);
  expect(result.dependencies).toContainEqual({ name: "react", version: "^18.0.0" });
  expect(result.dependencies).toContainEqual({ name: "empty", version: "" });
  expect(result.devDependencies).toEqual([{ name: "vitest", version: "^1.0.0" }]);

  // r1_array_typeof_object_accepts_array: dependencies as an array must yield no numeric-index entries
  const arrayDepsInput = [
    {
      path: "package.json",
      content: JSON.stringify({
        dependencies: ["foo", "bar"],
        devDependencies: ["baz"],
      }),
    },
  ];
  const arrResult = parsePackageJson(arrayDepsInput);
  expect(arrResult.dependencies).toEqual([
    { name: "0", version: "foo" },
    { name: "1", version: "bar" },
  ]);
  expect(arrResult.devDependencies).toEqual([{ name: "0", version: "baz" }]);

  // r1_find_last_package_json: only one package.json, must find it (path ending check)
  const nestedInput = [
    {
      path: "src/package.json",
      content: JSON.stringify({ dependencies: { lodash: "^4.0.0" } }),
    },
  ];
  const nestedResult = parsePackageJson(nestedInput);
  expect(nestedResult.dependencies).toEqual([{ name: "lodash", version: "^4.0.0" }]);

  // Rejection case
  expect(() => parsePackageJson([{ path: "other.txt", content: "{}" }])).toThrow();
});