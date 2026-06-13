import { parsePackageJson } from "./impl";
import { test, expect } from "vitest";

test("parsePackageJson handles various edge cases and bugs correctly", () => {
  const validPackageJson = JSON.stringify({
    name: "test-package",
    version: "1.0.0",
    dependencies: {
      lodash: "^4.17.21",
      react: "18.2.0",
    },
    devDependencies: {
      typescript: "^5.0.0",
      vitest: "^1.0.0",
    },
  });

  const inputWithValidPackageJson = [
    { path: "package.json", content: validPackageJson },
  ];

  // Correct behavior: returns parsed dependencies and devDependencies
  const result = parsePackageJson(inputWithValidPackageJson);
  expect(result.dependencies).toHaveLength(2);
  expect(result.devDependencies).toHaveLength(2);
  expect(result.dependencies[0].name).toBe("lodash");
  expect(result.dependencies[0].version).toBe("^4.17.21");
  expect(result.devDependencies[1].name).toBe("vitest");
  expect(result.devDependencies[1].version).toBe("^1.0.0");

  // Test for endswith_wrong_path: should fail on file named mypackage.json
  const inputWithWrongPath = [
    { path: "mypackage.json", content: validPackageJson },
  ];
  expect(() => parsePackageJson(inputWithWrongPath)).toThrow();

  // Test for flipped_version_typecheck: should not include non-string versions
  const invalidVersionJson = JSON.stringify({
    dependencies: {
      bad: null,
      good: "1.0.0",
    },
  });
  const inputWithInvalidVersion = [
    { path: "package.json", content: invalidVersionJson },
  ];
  const resultWithInvalidVersion = parsePackageJson(inputWithInvalidVersion);
  expect(resultWithInvalidVersion.dependencies).toHaveLength(1);
  expect(resultWithInvalidVersion.dependencies[0].name).toBe("good");

  // Test for dev_uses_dependencies: should not include devDependencies in dependencies
  const inputWithDevInDependencies = [
    { path: "package.json", content: JSON.stringify({
      dependencies: { dev: "1.0.0" },
      devDependencies: { dev: "2.0.0" },
    }) },
  ];
  const resultWithDevInDependencies = parsePackageJson(inputWithDevInDependencies);
  expect(resultWithDevInDependencies.dependencies).toHaveLength(1);
  expect(resultWithDevInDependencies.dependencies[0].name).toBe("dev");
  expect(resultWithDevInDependencies.dependencies[0].version).toBe("1.0.0");
  expect(resultWithDevInDependencies.devDependencies).toHaveLength(1);
  expect(resultWithDevInDependencies.devDependencies[0].name).toBe("dev");
  expect(resultWithDevInDependencies.devDependencies[0].version).toBe("2.0.0");

  // Test for dropped_missing_guard: should throw when package.json is missing
  const inputWithoutPackageJson = [
    { path: "other.json", content: "{}" },
  ];
  expect(() => parsePackageJson(inputWithoutPackageJson)).toThrow();

  // Test for swapped_return_fields: should return correct dependency fields
  const inputWithSwappedFields = [
    { path: "package.json", content: JSON.stringify({
      dependencies: { a: "1.0.0" },
      devDependencies: { b: "2.0.0" },
    }) },
  ];
  const resultWithSwappedFields = parsePackageJson(inputWithSwappedFields);
  expect(resultWithSwappedFields.dependencies).toHaveLength(1);
  expect(resultWithSwappedFields.dependencies[0].name).toBe("a");
  expect(resultWithSwappedFields.devDependencies).toHaveLength(1);
  expect(resultWithSwappedFields.devDependencies[0].name).toBe("b");
});