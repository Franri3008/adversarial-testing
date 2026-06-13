import { test, expect } from "vitest";
import { parsePackageWithVersion } from "./impl";

test("parsePackageWithVersion handles regular and scoped packages with and without versions", () => {
  // Regular package with version
  expect(parsePackageWithVersion("lodash@4.17.21")).toEqual({
    name: "lodash",
    version: "4.17.21",
  });

  // Regular package without version (catches regular_no_at_guard_flipped)
  expect(parsePackageWithVersion("lodash")).toEqual({
    name: "lodash",
    version: "latest",
  });

  // Scoped package with version (catches version_off_by_one_includes_at, scope_off_by_one_excludes_slash)
  expect(parsePackageWithVersion("@types/node@18.0.0")).toEqual({
    name: "@types/node",
    version: "18.0.0",
  });

  // Scoped package without version (catches scope_default_version_changed)
  expect(parsePackageWithVersion("@types/node")).toEqual({
    name: "@types/node",
    version: "latest",
  });

  // Scoped package with multiple @ signs (catches scope_uses_lastindexof)
  expect(parsePackageWithVersion("@scope/name@1.0.0@extra")).toEqual({
    name: "@scope/name",
    version: "1.0.0@extra",
  });
});