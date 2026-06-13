import { getLatestVersion } from "./impl";
import { test, expect } from "vitest";

test("getLatestVersion returns correct latest version and handles edge cases", () => {
  // Correct behavior: returns highest version, handles empty array, ties, prereleases
  expect(getLatestVersion(["1.0.0", "2.0.0", "1.1.0"])).toBe("2.0.0");
  expect(getLatestVersion(["1.0.0", "1.0.0"])).toBe("1.0.0");
  expect(getLatestVersion(["1.0.0-alpha", "1.0.0"])).toBe("1.0.0");
  expect(getLatestVersion(["1.0.0", "1.0.0-beta"])).toBe("1.0.0");
  expect(getLatestVersion(["1.0.0-beta", "1.0.0-alpha"])).toBe("1.0.0-beta");
  expect(getLatestVersion([])).toBeUndefined();

  // Test that it throws on invalid inputs (if any)
  expect(() => getLatestVersion(null as any)).toThrow();
  expect(() => getLatestVersion(undefined as any)).toThrow();
  expect(() => getLatestVersion([null as any])).toThrow();
  expect(() => getLatestVersion([undefined as any])).toThrow();

  // Test single element
  expect(getLatestVersion(["1.0.0"])).toBe("1.0.0");

  // Test with prerelease versions
  expect(getLatestVersion(["1.0.0-alpha", "1.0.0-beta", "1.0.0"])).toBe("1.0.0");
  expect(getLatestVersion(["1.0.0-alpha", "1.0.0-alpha.1"])).toBe("1.0.0-alpha.1");
});