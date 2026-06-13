import { test, expect } from "vitest";
import { parsePackageJson } from "./impl";

test("parsePackageJson targets path matching and devDeps guard bugs", () => {
  // endswith_to_includes: a file whose path contains "package.json" but does not
  // end with it should NOT be matched. With only this decoy file, no valid
  // package.json is found, so it must throw.
  expect(() =>
    parsePackageJson([
      { path: "package.json.bak", content: '{"dependencies":{}}' },
    ] as any),
  ).toThrow();

  // drop_devdeps_guard: devDependencies as a non-object (string) must not crash;
  // it should simply yield empty devDependencies.
  const result = parsePackageJson([
    {
      path: "/package.json",
      content: JSON.stringify({
        dependencies: { left: "1.0.0", right: "^2.3.4" },
        devDependencies: "not-an-object",
      }),
    },
  ] as any);

  expect(result.dependencies).toEqual([
    { name: "left", version: "1.0.0" },
    { name: "right", version: "^2.3.4" },
  ]);
  expect(result.devDependencies).toEqual([]);
});