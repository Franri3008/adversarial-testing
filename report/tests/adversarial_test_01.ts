import { compareVersions } from "./impl";
import { test, expect } from "vitest";

test("compareVersions handles various cases correctly", () => {
  // flipped_gt_comparison
  expect(compareVersions("2.0.0", "1.0.0")).toBe(1);
  expect(compareVersions("1.0.0", "2.0.0")).toBe(-1);

  // off_by_one_loop and min_instead_of_max
  expect(compareVersions("1.0.1", "1.0")).toBe(1);
  expect(compareVersions("1.0", "1.0.1")).toBe(-1);
  expect(compareVersions("1.0.0.1", "1.0.0")).toBe(1);
  expect(compareVersions("1.0.0", "1.0.0.1")).toBe(-1);

  // prerelease_swapped
  expect(compareVersions("1.0.0", "1.0.0-alpha")).toBe(1);
  expect(compareVersions("1.0.0-alpha", "1.0.0")).toBe(-1);

  // wrong_regex_group
  expect(compareVersions("1.2.10-alpha", "1.2.9")).toBe(1);
  expect(compareVersions("1.2.9", "1.2.10-alpha")).toBe(-1);
  expect(compareVersions("1.2.3-alpha", "1.2.3")).toBe(-1);
  expect(compareVersions("1.2.3", "1.2.3-alpha")).toBe(1);

  // equal versions
  expect(compareVersions("1.0.0", "1.0.0")).toBe(0);
  expect(compareVersions("1.0.0-alpha", "1.0.0-alpha")).toBe(0);
});