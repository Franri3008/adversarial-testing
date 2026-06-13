import { parsePackageWithVersion } from "./impl";
import { test, expect } from "vitest";

test("parsePackageWithVersion handles edge cases for scoped and regular packages", () => {
  // Bug r1_scope_no_slash_default_empty_version: invalid scoped package without slash should return 'latest' version
  expect(parsePackageWithVersion("@scope")).toEqual({ name: "@scope", version: "latest" });

  // Bug r1_regular_version_empty_when_trailing_at: regular package ending with '@' should yield empty version string
  expect(parsePackageWithVersion("lodash@")).toEqual({ name: "lodash", version: "" });
});