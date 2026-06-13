import { test, expect } from "vitest";
import { compareVersions } from "./impl";

test("compareVersions handles leading zeros and prerelease detection in any segment", () => {
  // Major.minor.patch comparison
  expect(compareVersions("1.0.0", "1.0.0")).toBe(0);
  expect(compareVersions("2.0.0", "1.0.0")).toBe(1);
  expect(compareVersions("1.0.0", "2.0.0")).toBe(-1);

  // Leading-zero parts must be parsed as base-10, not octal.
  // "1.08" -> minor 8, "1.07" -> minor 7, so 1.08 > 1.07
  expect(compareVersions("1.08", "1.07")).toBe(1);
  expect(compareVersions("1.07", "1.08")).toBe(-1);
  expect(compareVersions("1.09", "1.9")).toBe(0);

  // Prerelease in patch segment: 1.0.0-rc is lower than 1.0.0
  expect(compareVersions("1.0.0", "1.0.0-rc")).toBe(1);
  expect(compareVersions("1.0.0-rc", "1.0.0")).toBe(-1);

  // Prerelease dash NOT in the first segment: "1.0-x.0" has a dash,
  // so it must be treated as prerelease and be lower than "1.0.0".
  // Numeric parts: 1.0.0 vs 1.0.0 (the "-x" suffix on the second segment
  // is stripped to 0), then prerelease lowers 1.0-x.0.
  expect(compareVersions("1.0.0", "1.0-x.0")).toBe(1);
  expect(compareVersions("1.0-x.0", "1.0.0")).toBe(-1);
});