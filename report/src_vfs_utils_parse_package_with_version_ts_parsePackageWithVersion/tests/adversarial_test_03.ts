import { parsePackageWithVersion } from "./impl";
import { test, expect } from "vitest";

test("parsePackageWithVersion adversarial", () => {
  // r1_scope_empty_string / lastIndexOf for scope slash: deeper paths
  expect(parsePackageWithVersion("@scope/sub/pkg@1.0.0")).toEqual({
    name: "@scope/sub/pkg",
    version: "1.0.0",
  });

  // r1_scope_version_lastindexof: first @ after slash is the version separator
  expect(parsePackageWithVersion("@scope/pkg@1@2")).toEqual({
    name: "@scope/pkg",
    version: "1@2",
  });

  // r1_scope_at_zero_treated_no_version: version @ at index 0 after slash
  expect(parsePackageWithVersion("@scope/@x")).toEqual({
    name: "@scope/",
    version: "x",
  });

  // r1_regular_empty_version_default: @ as last char -> empty version, not 'latest'
  expect(parsePackageWithVersion("lodash@")).toEqual({
    name: "lodash",
    version: "",
  });

  // r1_empty_input_no_guard: empty string treated as regular, name '' version 'latest'
  expect(parsePackageWithVersion("")).toEqual({
    name: "",
    version: "latest",
  });

  // Basic regular case
  expect(parsePackageWithVersion("lodash@4.17.21")).toEqual({
    name: "lodash",
    version: "4.17.21",
  });

  // Regular package no version
  expect(parsePackageWithVersion("lodash")).toEqual({
    name: "lodash",
    version: "latest",
  });

  // Scoped no version
  expect(parsePackageWithVersion("@types/node")).toEqual({
    name: "@types/node",
    version: "latest",
  });

  // Scoped with version
  expect(parsePackageWithVersion("@types/node@18.0.0")).toEqual({
    name: "@types/node",
    version: "18.0.0",
  });

  // Scoped no slash -> latest
  expect(parsePackageWithVersion("@scope")).toEqual({
    name: "@scope",
    version: "latest",
  });
});