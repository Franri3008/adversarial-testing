import { parsePackageJson } from "./impl";
import { test, expect } from "vitest";

test("parsePackageJson handles deps, devDeps, types, and nested paths", () => {
  const packageJson = {
    dependencies: {
      react: "^18.0.0",
      lodash: "^4.0.0",
      badVersion: 123, // non-string, must be skipped
    },
    devDependencies: {
      vitest: "^1.0.0",
      typescript: "^5.0.0",
    },
  };

  // wrong_path_match: nested path requires endsWith, not startsWith
  const result = parsePackageJson([
    { path: "some/nested/dir/package.json", content: JSON.stringify(packageJson) },
  ]);

  // dep_guard_or + flip_type_check: only string versions in dependencies
  expect(result.dependencies).toHaveLength(2);
  expect(result.dependencies).toContainEqual({ name: "react", version: "^18.0.0" });
  expect(result.dependencies).toContainEqual({ name: "lodash", version: "^4.0.0" });
  // badVersion (non-string) must NOT be present
  expect(result.dependencies.some((d) => d.name === "badVersion")).toBe(false);

  // swap_deps_dev: devDeps must go to devDependencies, not dependencies
  expect(result.devDependencies).toHaveLength(2);
  expect(result.devDependencies).toContainEqual({ name: "vitest", version: "^1.0.0" });
  expect(result.devDependencies).toContainEqual({ name: "typescript", version: "^5.0.0" });
  // dependencies must not contain devDeps
  expect(result.dependencies.some((d) => d.name === "vitest")).toBe(false);
  expect(result.dependencies.some((d) => d.name === "typescript")).toBe(false);

  // drop_dev_guard: non-object devDependencies must not crash, yields empty
  const result2 = parsePackageJson([
    {
      path: "package.json",
      content: JSON.stringify({
        dependencies: { foo: "1.0.0" },
        devDependencies: "not-an-object",
      }),
    },
  ]);
  expect(result2.dependencies).toEqual([{ name: "foo", version: "1.0.0" }]);
  expect(result2.devDependencies).toEqual([]);

  // dep_guard_or: non-object dependencies must not crash, yields empty
  const result3 = parsePackageJson([
    {
      path: "/package.json",
      content: JSON.stringify({
        dependencies: "not-an-object",
        devDependencies: { bar: "2.0.0" },
      }),
    },
  ]);
  expect(result3.dependencies).toEqual([]);
  expect(result3.devDependencies).toEqual([{ name: "bar", version: "2.0.0" }]);
});