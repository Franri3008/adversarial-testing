import { test, expect } from "vitest";
import { compareVersions } from "./impl";

test("compareVersions targets specific mutation bugs", () => {
  // r1_min_instead_of_max_loop: trailing parts beyond shorter version must be compared
  expect(compareVersions("1.0.1", "1.0")).toBe(1);
  expect(compareVersions("1.0", "1.0.1")).toBe(-1);

  // r1_radix_dropped_parseInt: leading-zero parts must parse as decimal
  expect(compareVersions("1.08", "1.7")).toBe(1);
  expect(compareVersions("1.09", "1.10")).toBe(-1);

  // r1_prerelease_detection / release-vs-prerelease ordering
  expect(compareVersions("1.0.0", "1.0.0-rc")).toBe(1);
  expect(compareVersions("1.0.0-rc", "1.0.0")).toBe(-1);

  // basic ordering still holds
  expect(compareVersions("2.0.0", "1.9.9")).toBe(1);
  expect(compareVersions("1.2.3", "1.2.3")).toBe(0);

  // both prerelease, same numeric -> reference returns 0
  expect(compareVersions("1.0.0-alpha", "1.0.0-alpha")).toBe(0);
});