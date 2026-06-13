import { parsePackageWithVersion } from "./impl";
import { test, expect } from "vitest";

test("scoped package with multiple @ after scope uses first @ as version separator", () => {
  const result = parsePackageWithVersion("@scope/pkg@1.0.0@beta");
  expect(result).toEqual({ name: "@scope/pkg", version: "1.0.0@beta" });
});