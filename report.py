"""Assemble a run report: convergence graph + markdown summary + the generated tests.

Dependency-free. Writes a self-contained `report/` folder so a run against any repo
produces an artifact a human can read: what was targeted, how the suite hardened over
tokens (the graph), and the actual adversarial tests the loop wrote (the changes).
"""
import json
import os
import struct
import zlib
from typing import Any, Dict, List, Optional

WIDTH = 900
HEIGHT = 540
MARGIN_LEFT = 78
MARGIN_RIGHT = 40
MARGIN_TOP = 40
MARGIN_BOTTOM = 64

INK = (32, 39, 55)
GRID = (228, 232, 240)
KILL = (16, 163, 74)
BASELINE = (220, 38, 38)


def _set_pixel(pixels: bytearray, x: int, y: int, color) -> None:
    if x < 0 or x >= WIDTH or y < 0 or y >= HEIGHT:
        return
    index = (y * WIDTH + x) * 3;
    pixels[index:index + 3] = bytes(color);


def _draw_line(pixels: bytearray, x0: int, y0: int, x1: int, y1: int, color) -> None:
    dx = abs(x1 - x0);
    dy = -abs(y1 - y0);
    sx = 1 if x0 < x1 else -1;
    sy = 1 if y0 < y1 else -1;
    err = dx + dy;
    while True:
        _set_pixel(pixels, x0, y0, color);
        if x0 == x1 and y0 == y1:
            break
        doubled = 2 * err;
        if doubled >= dy:
            err += dy;
            x0 += sx;
        if doubled <= dx:
            err += dx;
            y0 += sy;


def _draw_disc(pixels: bytearray, cx: int, cy: int, radius: int, color) -> None:
    for y in range(cy - radius, cy + radius + 1):
        for x in range(cx - radius, cx + radius + 1):
            if (x - cx) * (x - cx) + (y - cy) * (y - cy) <= radius * radius:
                _set_pixel(pixels, x, y, color);


def _draw_cross(pixels: bytearray, cx: int, cy: int, radius: int, color) -> None:
    _draw_line(pixels, cx - radius, cy - radius, cx + radius, cy + radius, color);
    _draw_line(pixels, cx - radius, cy + radius, cx + radius, cy - radius, color);


def _write_png(path: str, pixels: bytearray) -> None:
    raw = bytearray();
    row_width = WIDTH * 3;
    for y in range(HEIGHT):
        raw.append(0);
        start = y * row_width;
        raw.extend(pixels[start:start + row_width]);
    def chunk(kind: bytes, data: bytes) -> bytes:
        checksum = zlib.crc32(kind + data) & 0xffffffff;
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)
    header = struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0);
    payload = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b"");
    with open(path, "wb") as handle:
        handle.write(payload);


def render_convergence(path: str, entries: List[Dict[str, Any]], baseline: Optional[Dict[str, Any]]) -> None:
    pixels = bytearray([255] * WIDTH * HEIGHT * 3);
    xs = [int(e.get("cumulative_tokens", 0)) for e in entries];
    base_x = int(baseline.get("cumulative_tokens", 0)) if baseline else 0;
    max_x = max(xs + [base_x, 1]);
    plot_w = WIDTH - MARGIN_LEFT - MARGIN_RIGHT;
    plot_h = HEIGHT - MARGIN_TOP - MARGIN_BOTTOM;

    def point(x_value: float, y_value: float):
        x = MARGIN_LEFT + int((x_value / max_x) * plot_w);
        y = HEIGHT - MARGIN_BOTTOM - int(max(0.0, min(1.0, y_value)) * plot_h);
        return x, y

    for step in range(0, 6):
        gy = HEIGHT - MARGIN_BOTTOM - int((step / 5) * plot_h);
        _draw_line(pixels, MARGIN_LEFT, gy, WIDTH - MARGIN_RIGHT, gy, GRID);
    _draw_line(pixels, MARGIN_LEFT, MARGIN_TOP, MARGIN_LEFT, HEIGHT - MARGIN_BOTTOM, INK);
    _draw_line(pixels, MARGIN_LEFT, HEIGHT - MARGIN_BOTTOM, WIDTH - MARGIN_RIGHT, HEIGHT - MARGIN_BOTTOM, INK);

    kill_points = [point(e.get("cumulative_tokens", 0), e.get("kill_rate", 0.0)) for e in entries];
    for index in range(1, len(kill_points)):
        x0, y0 = kill_points[index - 1];
        x1, y1 = kill_points[index];
        _draw_line(pixels, x0, y0, x1, y1, KILL);
    for x, y in kill_points:
        _draw_disc(pixels, x, y, 5, KILL);

    if baseline:
        bx, by = point(baseline.get("cumulative_tokens", 0), baseline.get("kill_rate", 0.0));
        _draw_cross(pixels, bx, by, 9, BASELINE);
    _write_png(path, pixels);


_EXT = {"python": "py", "typescript": "ts"};


def _suite_filename(language: str, index: int) -> str:
    return "adversarial_test_{:02d}.{}".format(index, _EXT.get(language, "txt"))


def _metric_entries(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        entry for entry in entries
        if "kill_rate" in entry and (entry.get("event") in (None, "iteration_completed", "run_finished"))
    ]


def _final_kill_rate(entries: List[Dict[str, Any]]) -> float:
    finished = [entry for entry in entries if entry.get("event") == "run_finished"]
    if finished:
        return finished[-1].get("kill_rate", 0.0)
    metrics = _metric_entries(entries)
    return metrics[-1].get("kill_rate", 0.0) if metrics else 0.0


def _last_event(entries: List[Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
    matches = [entry for entry in entries if entry.get("event") == name]
    return matches[-1] if matches else None


def _md(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _language_fence(language: str) -> str:
    if language == "typescript":
        return "ts"
    if language == "python":
        return "python"
    return ""


def _collect_mutants(entries: List[Dict[str, Any]], meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    for entry in entries:
        for mutant in entry.get("mutants") or []:
            mid = mutant.get("id")
            if not mid:
                continue
            existing = by_id.get(mid, {})
            merged = dict(existing)
            merged.update({k: v for k, v in mutant.items() if v not in (None, "")})
            merged["status"] = mutant.get("status") or existing.get("status") or "generated"
            by_id[mid] = merged
        for mutant in entry.get("killed_mutants") or []:
            mid = mutant.get("id")
            if mid:
                by_id[mid] = {**by_id.get(mid, {}), **mutant, "status": "killed"}
        for mutant in entry.get("surviving_mutants") or []:
            mid = mutant.get("id")
            if mid:
                by_id[mid] = {**by_id.get(mid, {}), **mutant, "status": "surviving"}

    for mutant in meta.get("surviving") or []:
        mid = mutant.get("id")
        if mid:
            by_id[mid] = {**by_id.get(mid, {}), **mutant, "status": "surviving"}
    return sorted(by_id.values(), key=lambda item: item.get("id", ""))


def _target_from_events(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    started = _last_event(entries, "run_started") or {}
    return started.get("target") or {}


def _markdown(meta: Dict[str, Any], entries: List[Dict[str, Any]], baseline: Optional[Dict[str, Any]], suite_files: List[str]) -> str:
    final = _final_kill_rate(entries);
    base_kr = baseline.get("kill_rate", 0.0) if baseline else 0.0;
    target = {**_target_from_events(entries), **meta}
    mutants = _collect_mutants(entries, meta)
    total_mutants = meta.get("total_mutants", len(mutants));
    finished = _last_event(entries, "run_finished") or {}
    stop_reason = meta.get("stop_reason") or finished.get("stop_reason", "-")
    metrics = _metric_entries(entries)
    accepted_fixes = [entry for entry in entries if entry.get("event") == "fix_accepted"]
    rejected_fixes = [entry for entry in entries if entry.get("event") == "fix_rejected"]
    generated_mutant_events = [entry for entry in entries if entry.get("event") == "mutants_generated"]
    language = target.get("language", meta.get("language", "python"))
    fence = _language_fence(language)
    lines = [];
    lines.append("# Adversarial test-hardening report");
    lines.append("");
    lines.append("## Target");
    lines.append("");
    lines.append("| | |");
    lines.append("|---|---|");
    lines.append("| repo | `{}` |".format(target.get("repo", "(built-in fixture)")));
    lines.append("| file | `{}` |".format(target.get("file", "-")));
    lines.append("| function | `{}` |".format(target.get("function", "-")));
    lines.append("| language | {} |".format(target.get("language", "-")));
    lines.append("| strategy model | `{}` |".format(meta.get("strategy_model", "-")));
    lines.append("| bulk model | `{}` |".format(meta.get("bulk_model", "-")));
    lines.append("");
    lines.append("## Result");
    lines.append("");
    lines.append("![convergence](convergence.png)");
    lines.append("");
    lines.append("- **Baseline (one cold-start test):** {:.0%} kill rate".format(base_kr));
    lines.append("- **Final (hardened suite):** {:.0%} kill rate over {} mutants".format(final, total_mutants));
    lines.append("- **Gain from looping:** +{:.0%}".format(max(0.0, final - base_kr)));
    if meta.get("mutant_rounds"):
        lines.append("- **Co-evolution:** {} adversary round(s); {} distinct bugs caught across waves".format(
            meta.get("mutant_rounds"), meta.get("killed_total", "?")));
        lines.append("  (the adversary kept inventing bugs the suite missed; each wave is a dip-then-recover in the graph above)");
    lines.append("- **Stop reason:** `{}`".format(stop_reason));
    last_metric = metrics[-1] if metrics else (entries[-1] if entries else {});
    if last_metric:
        lines.append("- **Tokens spent:** {:,}".format(int(last_metric.get("cumulative_tokens", 0))));
        if "cost_usd" in last_metric:
            lines.append("- **Cost:** ${:.4f}".format(last_metric["cost_usd"]));
    lines.append("");
    lines.append("## Run status");
    lines.append("");
    lines.append("| event | phase | iteration | status | detail |");
    lines.append("|---|---|---|---|---|");
    for entry in entries:
        if not entry.get("event"):
            continue
        detail = entry.get("stop_reason") or entry.get("note") or entry.get("reason") or ""
        if entry.get("event") == "mutants_generated":
            detail = "{} mutant(s)".format(entry.get("total_mutants", len(entry.get("mutants") or [])))
        lines.append("| {} | {} | {} | {} | {} |".format(
            _md(entry.get("event", "-")),
            _md(entry.get("phase", "-")),
            _md(entry.get("iteration", "-")),
            _md(entry.get("status", "-")),
            _md(detail or "-"),
        ));
    lines.append("");
    lines.append("## Progress per iteration");
    lines.append("");
    lines.append("| iter | tier | cum. tokens | kill rate | killed this round |");
    lines.append("|---|---|---|---|---|");
    for e in metrics:
        if e.get("event") == "run_finished":
            continue
        killed = e.get("killed_this_round") or [];
        lines.append("| {} | {} | {:,} | {:.0%} | {} |".format(
            e.get("iteration", "-"), e.get("tier", "-"), int(e.get("cumulative_tokens", 0)),
            e.get("kill_rate", 0.0), ", ".join(killed) if killed else "—"));
    lines.append("");
    lines.append("## Mutants generated");
    lines.append("");
    if mutants:
        lines.append("| id | status | description |");
        lines.append("|---|---|---|");
        for mutant in mutants:
            lines.append("| `{}` | {} | {} |".format(
                _md(mutant.get("id", "?")),
                _md(mutant.get("status", "generated")),
                _md(mutant.get("description", "")),
            ));
    elif generated_mutant_events:
        lines.append("Mutant generation events were recorded, but no valid mutants were retained.");
    else:
        lines.append("No mutant details were recorded in this log.");
    lines.append("");
    for mutant in mutants:
        if mutant.get("src"):
            lines.append("<details>");
            lines.append("<summary>{} source</summary>".format(mutant.get("id", "?")));
            lines.append("");
            lines.append("```{}".format(fence));
            lines.append(mutant.get("src", ""));
            lines.append("```");
            lines.append("");
            lines.append("</details>");
            lines.append("");
    lines.append("## Fixes accepted");
    lines.append("");
    if accepted_fixes:
        for entry in accepted_fixes:
            bug = entry.get("bug") or {};
            lines.append("### `{}`".format(bug.get("id", "fix")));
            lines.append("");
            lines.append("- Description: {}".format(bug.get("description", "")));
            lines.append("- Iteration: {}".format(entry.get("iteration", "-")));
            lines.append("");
            if entry.get("generated_test_src"):
                lines.append("Generated test:");
                lines.append("");
                lines.append("```{}".format(fence));
                lines.append(entry["generated_test_src"]);
                lines.append("```");
                lines.append("");
            if entry.get("final_code"):
                lines.append("Accepted fixed source:");
                lines.append("");
                lines.append("```{}".format(fence));
                lines.append(entry["final_code"]);
                lines.append("```");
                lines.append("");
    else:
        lines.append("No accepted fixes were recorded.");
    lines.append("");
    lines.append("## Fixes rejected");
    lines.append("");
    if rejected_fixes:
        lines.append("| iter | bug | reason |");
        lines.append("|---|---|---|");
        for entry in rejected_fixes:
            bug = entry.get("bug") or {};
            lines.append("| {} | `{}` | {} |".format(
                entry.get("iteration", "-"),
                _md(bug.get("id", "?")),
                _md(entry.get("reason", "")),
            ));
    else:
        lines.append("No rejected fixes were recorded.");
    lines.append("");
    lines.append("## Generated adversarial tests (the changes)");
    lines.append("");
    if suite_files:
        lines.append("The loop wrote {} test(s) into this suite:".format(len(suite_files)));
        lines.append("");
        for name in suite_files:
            lines.append("- [`{}`](tests/{})".format(name, name));
    else:
        lines.append("No tests were retained.");
    lines.append("");
    return "\n".join(lines)


def write_report(meta: Dict[str, Any], entries: List[Dict[str, Any]], suite_sources: List[str], baseline: Optional[Dict[str, Any]] = None, out_dir: str = "report") -> str:
    os.makedirs(out_dir, exist_ok=True);
    tests_dir = os.path.join(out_dir, "tests");
    os.makedirs(tests_dir, exist_ok=True);
    language = meta.get("language", "python");
    suite_files = [];
    for index, src in enumerate(suite_sources, start=1):
        name = _suite_filename(language, index);
        with open(os.path.join(tests_dir, name), "w") as handle:
            handle.write(src);
        suite_files.append(name);
    render_convergence(os.path.join(out_dir, "convergence.png"), _metric_entries(entries), baseline);
    markdown = _markdown(meta, entries, baseline, suite_files);
    report_path = os.path.join(out_dir, "report.md");
    with open(report_path, "w") as handle:
        handle.write(markdown);
    return report_path


def _slug(*parts: str) -> str:
    raw = "_".join(p for p in parts if p);
    return "".join(c if c.isalnum() else "_" for c in raw).strip("_") or "target"


def write_repo_report(repo: str, results: List[Dict[str, Any]], out_dir: str = "report") -> str:
    """Aggregate a whole-repo scan: one index + a per-target subreport (graph + tests)."""
    os.makedirs(out_dir, exist_ok=True);
    rows = [];
    total_tokens = 0;
    for res in results:
        slug = _slug(res.get("file", ""), res.get("function_name", ""));
        meta = {
            "repo": repo,
            "file": res.get("file", "-"),
            "function": res.get("function_name", "-"),
            "language": res.get("language", "-"),
            "strategy_model": res.get("strategy_model", "-"),
            "bulk_model": res.get("bulk_model", "-"),
            "total_mutants": res.get("total", 0),
            "surviving": res.get("surviving", []),
            "mutant_rounds": res.get("mutant_rounds", 0),
            "killed_total": res.get("killed_total", 0),
        };
        write_report(meta, res["entries"], res["suite_sources"], baseline=res.get("baseline"), out_dir=os.path.join(out_dir, slug));
        entries = res["entries"];
        base_kr = res.get("baseline", {}).get("kill_rate", 0.0) if res.get("baseline") else 0.0;
        final_kr = _final_kill_rate(entries);
        tokens = int(entries[-1].get("cumulative_tokens", 0)) if entries else 0;
        total_tokens += tokens;
        rows.append((res.get("function_name", "?"), res.get("file", "-"), base_kr, final_kr, res.get("total", 0), tokens, slug));

    mean_final = sum(r[3] for r in rows) / len(rows) if rows else 0.0;
    lines = [];
    lines.append("# Repo hardening report");
    lines.append("");
    lines.append("**Repo:** `{}`".format(repo));
    lines.append("");
    lines.append("Scanned for self-contained functions and hardened **{}** target(s).".format(len(rows)));
    lines.append("");
    lines.append("- **Mean final kill rate:** {:.0%}".format(mean_final));
    lines.append("- **Total tokens:** {:,}".format(total_tokens));
    lines.append("");
    lines.append("| function | file | baseline | final | mutants | tokens | details |");
    lines.append("|---|---|---|---|---|---|---|");
    for fn, fpath, base_kr, final_kr, mutants, tokens, slug in rows:
        lines.append("| `{}` | `{}` | {:.0%} | {:.0%} | {} | {:,} | [report]({}/report.md) |".format(
            fn, fpath, base_kr, final_kr, mutants, tokens, slug));
    lines.append("");
    index_path = os.path.join(out_dir, "report.md");
    with open(index_path, "w") as handle:
        handle.write("\n".join(lines));
    return index_path


def _read_jsonl(path: str) -> List[Dict[str, Any]]:
    entries = [];
    with open(path) as handle:
        for line in handle:
            stripped = line.strip();
            if stripped:
                entries.append(json.loads(stripped));
    return entries


def main() -> None:
    import sys
    log_path = "run.jsonl";
    for arg in sys.argv[1:]:
        if arg.startswith("log="):
            log_path = arg.split("=", 1)[1];
    if not os.path.isfile(log_path):
        print("no log at {}; run main.py first".format(log_path));
        return
    entries = _read_jsonl(log_path);
    target = _target_from_events(entries);
    mutants = _collect_mutants(entries, {});
    meta = {**target, "total_mutants": len(mutants)};
    path = write_report(meta, entries, [], baseline=None);
    print("wrote {}".format(path));


if __name__ == "__main__":
    main();
