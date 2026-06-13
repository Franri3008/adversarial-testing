import { parsePackageWithVersion } from "./impl";
import { test, expect } from "vitest";

test("parses regular package using first @ separator", () => {
  // A package name with multiple @ separators would differ between
  // indexOf (correct) and lastIndexOf (buggy mutation)
  const result = parsePackageWithVersion("foo@1.0.0@beta");
  expect(result.name).toBe("foo");
  expect(result.version).toBe("1.0.0@beta");

  const simple = parsePackageWithVersion("lodash@4.17.21");
  expect(simple.name).toBe("lodash");
  expect(simple.version).toBe("4.17.21");

  const another = parsePackageWithVersion("a@b@c");
  expect(another.name).toBe("a");
  expect(another.version).toBe("b@c");
});