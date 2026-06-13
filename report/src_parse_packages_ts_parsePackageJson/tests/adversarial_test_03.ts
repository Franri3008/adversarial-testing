import { parsePackageJson } from "./impl";
import { test, expect } from "vitest";

test("parsePackageJson handles valid package.json with dependencies and devDependencies", () => {
  const input: any[] = [
    {
      path: "package.json",
      content: JSON.stringify({
        name: "test-package",
        version: "1.0.0",
        dependencies: {
          lodash: "^4.17.21",
          react: "^18.2.0",
        },
        devDependencies: {
          typescript: "^5.0.0",
          vitest: "^1.0.0",
        },
      }),
    },
  ];

  const result = parsePackageJson(input);

  expect(result.dependencies).toEqual([
    { name: "lodash", version: "^4.17.21" },
    { name: "react", version: "^18.2.0" },
  ]);
  expect(result.devDependencies).toEqual([
    { name: "typescript", version: "^5.0.0" },
    { name: "vitest", version: "^1.0.0" },
  ]);

  // Test with path starting with slash
  const inputWithSlash = [
    {
      path: "/package.json",
      content: JSON.stringify({
        dependencies: { axios: "^1.0.0" },
        devDependencies: { jest: "^29.0.0" },
      }),
    },
  ];

  const resultWithSlash = parsePackageJson(inputWithSlash);
  expect(resultWithSlash.dependencies).toEqual([
    { name: "axios", version: "^1.0.0" },
  ]);
  expect(resultWithSlash.devDependencies).toEqual([
    { name: "jest", version: "^29.0.0" },
  ]);

  // Test with nested package.json
  const inputNested = [
    {
      path: "src/package.json",
      content: JSON.stringify({
        dependencies: { moment: "^2.29.4" },
      }),
    },
  ];

  const resultNested = parsePackageJson(inputNested);
  expect(resultNested.dependencies).toEqual([
    { name: "moment", version: "^2.29.4" },
  ]);
  expect(resultNested.devDependencies).toEqual([]);

  // Test with missing package.json
  expect(() => parsePackageJson([])).toThrow();
  expect(() => parsePackageJson([{ path: "other.json", content: "{}" }])).toThrow();

  // Test with malformed JSON
  const malformedInput = [
    {
      path: "package.json",
      content: "{ invalid json }",
    },
  ];
  expect(() => parsePackageJson(malformedInput)).toThrow();
});