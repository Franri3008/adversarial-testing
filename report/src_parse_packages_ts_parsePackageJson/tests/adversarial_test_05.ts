import { parsePackageJson } from "./impl";
import { test, expect } from "vitest";

test("parsePackageJson handles edge-case version strings and dep parsing", () => {
  const input = [
    {
      path: "/some/dir/package.json",
      content: JSON.stringify({
        dependencies: {
          "pkg-empty": "",
          "pkg-spaced": "  1.2.3  ",
          "pkg-normal": "^4.0.0",
        },
        devDependencies: {
          "dev-empty": "",
          "dev-normal": "~2.0.0",
        },
      }),
    },
  ];

  const result = parsePackageJson(input as any);

  // Empty-string versions must NOT be dropped (catches skip_empty_string)
  expect(result.dependencies).toContainEqual({ name: "pkg-empty", version: "" });
  expect(result.devDependencies).toContainEqual({
    name: "dev-empty",
    version: "",
  });

  // Whitespace must be preserved, not trimmed (catches trim_version)
  expect(result.dependencies).toContainEqual({
    name: "pkg-spaced",
    version: "  1.2.3  ",
  });

  expect(result.dependencies).toContainEqual({
    name: "pkg-normal",
    version: "^4.0.0",
  });
  expect(result.devDependencies).toContainEqual({
    name: "dev-normal",
    version: "~2.0.0",
  });

  // Exact counts ensure nothing dropped or added
  expect(result.dependencies.length).toBe(3);
  expect(result.devDependencies.length).toBe(2);
});