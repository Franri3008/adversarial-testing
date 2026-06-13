import { parsePackageWithVersion } from "./impl";
import { test, expect } from "vitest";

test("parsePackageWithVersion handles scoped and regular packages correctly", () => {
  // Scoped package with version: catches scope_end_off_by_one and version_include_at
  const scoped = parsePackageWithVersion("@types/node@18.0.0");
  expect(scoped.name).toBe("@types/node");
  expect(scoped.version).toBe("18.0.0");

  // Scoped package without version: catches wrong_default_version
  const scopedNoVer = parsePackageWithVersion("@types/node");
  expect(scopedNoVer.name).toBe("@types/node");
  expect(scopedNoVer.version).toBe("latest");

  // Scoped package where @ appears: ensures version separator is found after slash
  const scopedComplex = parsePackageWithVersion("@scope/pkg@1.2.3");
  expect(scopedComplex.name).toBe("@scope/pkg");
  expect(scopedComplex.version).toBe("1.2.3");

  // Regular package with version: catches lastindexof_at and version include
  const regular = parsePackageWithVersion("lodash@4.17.21");
  expect(regular.name).toBe("lodash");
  expect(regular.version).toBe("4.17.21");

  // Regular package without version: catches wrong_default_version
  const regularNoVer = parsePackageWithVersion("lodash");
  expect(regularNoVer.name).toBe("lodash");
  expect(regularNoVer.version).toBe("latest");

  // Package name that starts with @ is treated as scoped: catches flipped_scope_guard
  // "@foo" with no slash returns name unchanged, version latest
  const scopeNoSlash = parsePackageWithVersion("@foo");
  expect(scopeNoSlash.name).toBe("@foo");
  expect(scopeNoSlash.version).toBe("latest");
});