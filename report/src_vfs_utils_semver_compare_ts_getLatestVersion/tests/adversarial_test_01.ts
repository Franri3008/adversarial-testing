import { test, expect } from "vitest";
import { getLatestVersion } from "./impl";

test("getLatestVersion returns the highest semver version", () => {
  // Empty array should return undefined
  expect(getLatestVersion([])).toBeUndefined();

  // Single element array returns that element
  expect(getLatestVersion(["1.0.0"])).toBe("1.0.0");

  // Multiple versions: highest major wins
  expect(getLatestVersion(["1.0.0", "2.0.0", "1.5.0"])).toBe("2.0.0");

  // Prerelease versions are lower than release versions
  expect(getLatestVersion(["1.0.0-alpha", "1.0.0"])).toBe("1.0.0");
  expect(getLatestVersion(["1.0.0", "1.0.0-beta"])).toBe("1.0.0");

  // Tie: equal versions should return the first occurrence (reference uses > 0, not >= 0)
  expect(getLatestVersion(["1.0.0", "1.0.0"])).toBe("1.0.0");

  // Complex ordering with minor and patch
  expect(getLatestVersion(["1.2.3", "1.2.4", "1.1.9"])).toBe("1.2.4");
});