import { compareVersions } from "./impl";
import { test, expect } from "vitest";

test("compareVersions adversarial", () => {
  // Basic ordering
  expect(compareVersions("1.0.1", "1.0.0")).toBe(1);
  expect(compareVersions("1.0.0", "1.0.1")).toBe(-1);
  expect(compareVersions("1.0.0", "1.0.0")).toBe(0);

  // r1_radix_dropped: octal-like leading-zero parts must parse as base 10
  // "010" -> 10 (decimal). With radix dropped, parseInt("010") could give 8.
  expect(compareVersions("1.010.0", "1.8.0")).toBe(1);
  expect(compareVersions("0.010.0", "0.10.0")).toBe(0);

  // r1_prerelease_only_v1_check / includes vs startsWith for embedded markers
  // 1.0.0-alpha is a prerelease, lower than the release 1.0.0
  expect(compareVersions("1.0.0-alpha", "1.0.0")).toBe(-1);
  expect(compareVersions("1.0.0", "1.0.0-alpha")).toBe(1);

  // r1_regex_no_anchor: leading non-digit parts must coerce to 0 via ^ anchor.
  // "x5" with anchor -> no match -> 0; without anchor regex could match the "5".
  expect(compareVersions("1.x5.0", "1.0.0")).toBe(0);
  expect(compareVersions("1.x5.0", "1.4.0")).toBe(-1);

  // r1_zero_part_coalesce: malformed/missing parts must coalesce to 0 with ||.
  // "1" vs "1.0.0" should be equal (missing parts default to 0).
  expect(compareVersions("1", "1.0.0")).toBe(0);
  expect(compareVersions("2", "1.9.9")).toBe(1);

  // Prerelease markers on both -> equal numeric, both prerelease -> 0
  expect(compareVersions("1.0.0-alpha", "1.0.0-beta")).toBe(0);
});