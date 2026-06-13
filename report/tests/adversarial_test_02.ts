import { parsePackageJson } from "./impl";
import { test, expect } from "vitest";

test("parsePackageJson handles dependencies and devDependencies correctly and rejects invalid inputs", () => {
  // Valid package.json with both dependencies and devDependencies
  const validInput = [
    { path: "package.json", content: JSON.stringify({
      dependencies: { "lodash": "^4.17.21", "react": "18.2.0" },
      devDependencies: { "typescript": "^5.0.0", "vitest": "^1.0.0" }
    })}
  ];
  const validResult = parsePackageJson(validInput);
  expect(validResult.dependencies).toEqual([
    { name: "lodash", version: "^4.17.21" },
    { name: "react", version: "18.2.0" }
  ]);
  expect(validResult.devDependencies).toEqual([
    { name: "typescript", version: "^5.0.0" },
    { name: "vitest", version: "^1.0.0" }
  ]);

  // Missing dependencies key entirely
  const missingDepsInput = [
    { path: "package.json", content: JSON.stringify({
      devDependencies: { "typescript": "^5.0.0" }
    })}
  ];
  const missingDepsResult = parsePackageJson(missingDepsInput);
  expect(missingDepsResult.dependencies).toEqual([]);
  expect(missingDepsResult.devDependencies).toEqual([{ name: "typescript", version: "^5.0.0" }]);

  // Missing devDependencies key entirely
  const missingDevDepsInput = [
    { path: "package.json", content: JSON.stringify({
      dependencies: { "lodash": "^4.17.21" }
    })}
  ];
  const missingDevDepsResult = parsePackageJson(missingDevDepsInput);
  expect(missingDevDepsResult.dependencies).toEqual([{ name: "lodash", version: "^4.17.21" }]);
  expect(missingDevDepsResult.devDependencies).toEqual([]);

  // Dependencies present but not an object (string) - should not crash, returns empty
  const depsAsStringInput = [
    { path: "package.json", content: JSON.stringify({
      dependencies: "not-an-object",
      devDependencies: { "vitest": "^1.0.0" }
    })}
  ];
  const depsAsStringResult = parsePackageJson(depsAsStringInput);
  expect(depsAsStringResult.dependencies).toEqual([]);
  expect(depsAsStringResult.devDependencies).toEqual([{ name: "vitest", version: "^1.0.0" }]);

  // devDependencies present but not an object (string) - should not crash, returns empty
  const devDepsAsStringInput = [
    { path: "package.json", content: JSON.stringify({
      dependencies: { "lodash": "^4.17.21" },
      devDependencies: "not-an-object"
    })}
  ];
  const devDepsAsStringResult = parsePackageJson(devDepsAsStringInput);
  expect(devDepsAsStringResult.dependencies).toEqual([{ name: "lodash", version: "^4.17.21" }]);
  expect(devDepsAsStringResult.devDependencies).toEqual([]);

  // Dependencies present but null - should not crash (typeof null === 'object' but null check fails)
  const depsAsNullInput = [
    { path: "package.json", content: JSON.stringify({
      dependencies: null,
      devDependencies: { "vitest": "^1.0.0" }
    })}
  ];
  const depsAsNullResult = parsePackageJson(depsAsNullInput);
  expect(depsAsNullResult.dependencies).toEqual([]);
  expect(depsAsNullResult.devDependencies).toEqual([{ name: "vitest", version: "^1.0.0" }]);

  // No package.json found - should throw
  const noPackageJsonInput = [
    { path: "tsconfig.json", content: "{}" }
  ];
  expect(() => parsePackageJson(noPackageJsonInput)).toThrow("no package.json found in input files");

  // Invalid JSON - should throw
  const invalidJsonInput = [
    { path: "package.json", content: "{ invalid json" }
  ];
  expect(() => parsePackageJson(invalidJsonInput)).toThrow();

  // Empty package.json - should return empty arrays
  const emptyPackageJsonInput = [
    { path: "package.json", content: "{}" }
  ];
  const emptyResult = parsePackageJson(emptyPackageJsonInput);
  expect(emptyResult.dependencies).toEqual([]);
  expect(emptyResult.devDependencies).toEqual([]);

  // Dependencies with non-string versions - should skip non-string entries
  const nonStringVersionsInput = [
    { path: "package.json", content: JSON.stringify({
      dependencies: { "valid": "^1.0.0", "invalid": 123, "alsoInvalid": { "version": "1.0" } },
      devDependencies: { "validDev": "^2.0.0" }
    })}
  ];
  const nonStringResult = parsePackageJson(nonStringVersionsInput);
  expect(nonStringResult.dependencies).toEqual([{ name: "valid", version: "^1.0.0" }]);
  expect(nonStringResult.devDependencies).toEqual([{ name: "validDev", version: "^2.0.0" }]);
});