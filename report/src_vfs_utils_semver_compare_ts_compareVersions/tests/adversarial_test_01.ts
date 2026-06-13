import { compareVersions } from "./impl";
import { test, expect } from "vitest";

test("compareVersions catches target bugs", () => {
  // flipped_gt_comparison: "2.0.0" > "1.0.0" should return 1, not -1
  expect(compareVersions("2.0.0", "1.0.0")).toBe(1);

  // prerelease_swapped_return: release "1.0.0" > prerelease "1.0.0-alpha" should return 1, not -1
  expect(compareVersions("1.0.0", "1.0.0-alpha")).toBe(1);

  // wrong_default_part: "1.0" vs "1.0.0" should be equal (0), not affected by default 1
  expect(compareVersions("1.0", "1.0.0")).toBe(0);

  // equal_uses_gte: identical versions "1.0.0" vs "1.0.0" should return 0, not 1
  expect(compareVersions("1.0.0", "1.0.0")).toBe(0);

  // Additional sanity checks to ensure correct behavior isn't broken
  expect(compareVersions("1.0.0", "2.0.0")).toBe(-1);
  expect(compareVersions("1.0.0-alpha", "1.0.0")).toBe(-1);
  expect(compareVersions("1.0.1", "1.0.0")).toBe(1);
  expect(compareVersions("1.1.0", "1.0.9")).toBe(1);
});