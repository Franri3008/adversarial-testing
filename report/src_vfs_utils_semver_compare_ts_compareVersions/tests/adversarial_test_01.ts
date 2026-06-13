import { compareVersions } from "./impl";
import { test, expect } from "vitest";

test("compareVersions adversarial", () => {
  // flipped_gt_lt: v1 greater should return 1
  expect(compareVersions("2.0.0", "1.0.0")).toBe(1);
  expect(compareVersions("1.0.0", "2.0.0")).toBe(-1);

  // basic equality
  expect(compareVersions("1.2.3", "1.2.3")).toBe(0);

  // wrong_default_part: missing index should default to 0, so "1.0" == "1.0.0"
  expect(compareVersions("1.0", "1.0.0")).toBe(0);
  expect(compareVersions("1.0.0", "1.0")).toBe(0);
  // and "1.0.1" > "1.0" because missing defaults to 0 not 1
  expect(compareVersions("1.0.1", "1.0")).toBe(1);
  expect(compareVersions("1.0", "1.0.1")).toBe(-1);

  // off_by_one_loop: over-iteration would compare extra undefined parts.
  // With correct default 0, these remain equal; over-iteration with wrong
  // default could change result. Pair with default-part check.
  expect(compareVersions("1.2", "1.2")).toBe(0);

  // swapped_v2_separator: v2 must parse with "." separator
  expect(compareVersions("1.2.3", "1.2.4")).toBe(-1);
  expect(compareVersions("1.2.4", "1.2.3")).toBe(1);
  expect(compareVersions("0.0.0", "1.0.0")).toBe(-1);
  // if v2 used comma, "9.9.9" would parse as single part 9 vs v1 major
  expect(compareVersions("5.0.0", "9.9.9")).toBe(-1);

  // prerelease_flipped: release > prerelease should return 1
  expect(compareVersions("1.0.0", "1.0.0-alpha")).toBe(1);
  expect(compareVersions("1.0.0-alpha", "1.0.0")).toBe(-1);
  expect(compareVersions("1.0.0-alpha", "1.0.0-beta")).toBe(0);
});