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


def _final_kill_rate(entries: List[Dict[str, Any]]) -> float:
    return entries[-1].get("kill_rate", 0.0) if entries else 0.0


def _markdown(meta: Dict[str, Any], entries: List[Dict[str, Any]], baseline: Optional[Dict[str, Any]], suite_files: List[str]) -> str:
    final = _final_kill_rate(entries);
    base_kr = baseline.get("kill_rate", 0.0) if baseline else 0.0;
    total_mutants = meta.get("total_mutants", 0);
    lines = [];
    lines.append("# Adversarial test-hardening report");
    lines.append("");
    lines.append("## Target");
    lines.append("");
    lines.append("| | |");
    lines.append("|---|---|");
    lines.append("| repo | `{}` |".format(meta.get("repo", "(built-in fixture)")));
    lines.append("| file | `{}` |".format(meta.get("file", "-")));
    lines.append("| function | `{}` |".format(meta.get("function", "-")));
    lines.append("| language | {} |".format(meta.get("language", "-")));
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
    if entries:
        lines.append("- **Tokens spent:** {:,}".format(int(entries[-1].get("cumulative_tokens", 0))));
        if "cost_usd" in entries[-1]:
            lines.append("- **Cost:** ${:.4f}".format(entries[-1]["cost_usd"]));
    lines.append("");
    lines.append("## Progress per iteration");
    lines.append("");
    lines.append("| iter | tier | cum. tokens | kill rate | killed this round |");
    lines.append("|---|---|---|---|---|");
    for e in entries:
        killed = e.get("killed_this_round") or [];
        lines.append("| {} | {} | {:,} | {:.0%} | {} |".format(
            e.get("iteration", "-"), e.get("tier", "-"), int(e.get("cumulative_tokens", 0)),
            e.get("kill_rate", 0.0), ", ".join(killed) if killed else "—"));
    lines.append("");
    surviving = meta.get("surviving") or [];
    lines.append("## Mutants still surviving");
    lines.append("");
    if surviving:
        for m in surviving:
            lines.append("- `{}` — {}".format(m.get("id", "?"), m.get("description", "")));
    else:
        lines.append("None — every mutant was killed.");
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
    render_convergence(os.path.join(out_dir, "convergence.png"), entries, baseline);
    markdown = _markdown(meta, entries, baseline, suite_files);
    report_path = os.path.join(out_dir, "report.md");
    with open(report_path, "w") as handle:
        handle.write(markdown);
    return report_path


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
    meta = {"total_mutants": 0};
    path = write_report(meta, entries, [], baseline=None);
    print("wrote {}".format(path));


if __name__ == "__main__":
    main();
