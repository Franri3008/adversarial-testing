import json
import os
import struct
import zlib
from typing import Any, Dict, List, Optional

LOG_PATH = "run.jsonl"
BASELINE_PATH = "baseline.json"
PLOT_PATH = "repair_curve.png"
WIDTH = 900
HEIGHT = 560
MARGIN_LEFT = 72
MARGIN_RIGHT = 36
MARGIN_TOP = 36
MARGIN_BOTTOM = 64


def _read_entries(path: str) -> List[Dict[str, Any]]:
    entries = [];
    with open(path) as handle:
        for line in handle:
            stripped = line.strip();
            if stripped:
                entries.append(json.loads(stripped));
    return entries


def _read_baseline(path: str) -> Optional[Dict[str, Any]]:
    if not os.path.isfile(path):
        return None
    with open(path) as handle:
        stripped = handle.read().strip();
    if not stripped:
        return None
    return json.loads(stripped)


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


def _draw_circle(pixels: bytearray, cx: int, cy: int, radius: int, color) -> None:
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


def _total_bugs(entries: List[Dict[str, Any]], baseline: Optional[Dict[str, Any]]) -> int:
    if baseline and baseline.get("total_bugs"):
        return baseline["total_bugs"]
    return max([entry.get("bugs_fixed", 0) for entry in entries] + [1])


def _render_builtin_png(entries: List[Dict[str, Any]], baseline: Optional[Dict[str, Any]]) -> None:
    pixels = bytearray([255] * WIDTH * HEIGHT * 3);
    total_bugs = _total_bugs(entries, baseline);
    xs = [entry["cumulative_tokens"] for entry in entries];
    baseline_x = [baseline["cumulative_tokens"]] if baseline else [];
    max_x = max(xs + baseline_x + [1]);
    plot_width = WIDTH - MARGIN_LEFT - MARGIN_RIGHT;
    plot_height = HEIGHT - MARGIN_TOP - MARGIN_BOTTOM;

    def point(x_value: float, y_value: float):
        x = MARGIN_LEFT + int((x_value / max_x) * plot_width);
        y = HEIGHT - MARGIN_BOTTOM - int(y_value * plot_height);
        return x, y

    for step in range(0, 6):
        y = HEIGHT - MARGIN_BOTTOM - int((step / 5) * plot_height);
        _draw_line(pixels, MARGIN_LEFT, y, WIDTH - MARGIN_RIGHT, y, (228, 232, 240));
    _draw_line(pixels, MARGIN_LEFT, MARGIN_TOP, MARGIN_LEFT, HEIGHT - MARGIN_BOTTOM, (32, 39, 55));
    _draw_line(pixels, MARGIN_LEFT, HEIGHT - MARGIN_BOTTOM, WIDTH - MARGIN_RIGHT, HEIGHT - MARGIN_BOTTOM, (32, 39, 55));

    bug_points = [point(entry["cumulative_tokens"], entry["bugs_fixed"] / total_bugs) for entry in entries];
    kill_points = [point(entry["cumulative_tokens"], entry.get("kill_rate", 0.0)) for entry in entries];
    for series, color in ((bug_points, (37, 99, 235)), (kill_points, (16, 163, 74))):
        for index in range(1, len(series)):
            x0, y0 = series[index - 1];
            x1, y1 = series[index];
            _draw_line(pixels, x0, y0, x1, y1, color);
        for x, y in series:
            _draw_circle(pixels, x, y, 5, color);

    if baseline:
        bx, by = point(baseline["cumulative_tokens"], baseline["bugs_fixed"] / total_bugs);
        _draw_cross(pixels, bx, by, 9, (220, 38, 38));
    _write_png(PLOT_PATH, pixels);


def main() -> None:
    entries = _read_entries(LOG_PATH);
    if not entries:
        print("no entries found in {}; run python3 main.py first".format(LOG_PATH));
        return

    baseline = _read_baseline(BASELINE_PATH);
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        _render_builtin_png(entries, baseline);
        print("wrote {}".format(PLOT_PATH));
        return

    total_bugs = _total_bugs(entries, baseline);
    xs = [entry["cumulative_tokens"] for entry in entries];
    bugs = [entry["bugs_fixed"] for entry in entries];
    kills = [entry.get("kill_rate", 0.0) for entry in entries];

    fig, ax_bugs = plt.subplots(figsize=(8, 5));
    ax_bugs.plot(xs, bugs, marker="o", color="#2563eb", label="bugs fixed (loop)");
    if baseline:
        ax_bugs.scatter([baseline["cumulative_tokens"]], [baseline["bugs_fixed"]], color="red", marker="x", s=90, label="one-shot baseline");
    ax_bugs.set_xlabel("cumulative tokens");
    ax_bugs.set_ylabel("bugs fixed");
    ax_bugs.set_ylim(0, total_bugs + 0.5);
    ax_bugs.grid(True, alpha=0.3);

    ax_kill = ax_bugs.twinx();
    ax_kill.plot(xs, kills, marker="s", color="#10a34a", label="suite kill rate");
    ax_kill.set_ylabel("suite kill rate");
    ax_kill.set_ylim(0, 1.05);

    lines_bugs, labels_bugs = ax_bugs.get_legend_handles_labels();
    lines_kill, labels_kill = ax_kill.get_legend_handles_labels();
    ax_bugs.legend(lines_bugs + lines_kill, labels_bugs + labels_kill, loc="lower right");
    fig.tight_layout();
    fig.savefig(PLOT_PATH);
    print("wrote {}".format(PLOT_PATH));


if __name__ == "__main__":
    main();
