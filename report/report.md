# Repo hardening report

**Repo:** `fiberplane/honcpiler`

Scanned for self-contained functions and hardened **5** target(s).

- **Mean final kill rate:** 82%
- **Total tokens:** 152,367

| function | file | baseline | final | mutants | tokens | details |
|---|---|---|---|---|---|---|
| `compareVersions` | `src/vfs/utils/semver-compare.ts` | 100% | 89% | 9 | 39,951 | [report](src_vfs_utils_semver_compare_ts_compareVersions/report.md) |
| `parsePackageWithVersion` | `src/vfs/utils/parse-package-with-version.ts` | 100% | 86% | 7 | 24,837 | [report](src_vfs_utils_parse_package_with_version_ts_parsePackageWithVersion/report.md) |
| `parsePackageJson` | `src/parse-packages.ts` | 0% | 88% | 8 | 49,594 | [report](src_parse_packages_ts_parsePackageJson/report.md) |
| `getLatestVersion` | `src/vfs/utils/semver-compare.ts` | 0% | 60% | 5 | 22,515 | [report](src_vfs_utils_semver_compare_ts_getLatestVersion/report.md) |
| `main` | `scripts/py/main.py` | 100% | 89% | 9 | 15,470 | [report](scripts_py_main_py_main/report.md) |
