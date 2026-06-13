#!/usr/bin/env python3
import argparse
import functools
import json
import shutil
import sys
import threading
import time

RESET = "\033[0m"
USE_COLOR = True

CYAN   = (34, 211, 238)
PURPLE = (168, 85, 247)
GREEN  = (74, 222, 128)
RED    = (248, 113, 113)
YELLOW = (250, 204, 21)
ORANGE = (251, 146, 60)
WHITE  = (226, 232, 240)
GREY   = (107, 124, 147)
BORDER = (56, 140, 160)

SPIN = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
SPARKS = "▁▂▃▄▅▆▇█"

TITLE = "ADVERSARY"


def colorize(text, rgb=None, bold=False):
    if not USE_COLOR or text == "":
        return text
    pre = ""
    if bold:
        pre += "\033[1m"
    if rgb is not None:
        pre += "\033[38;2;{};{};{}m".format(*rgb)
    return pre + text + RESET if pre else text


def grad(text, c0, c1, total=None):
    """Horizontal RGB gradient across `text` (spaces left untouched)."""
    if not USE_COLOR:
        return text
    total = total or len(text)
    out = []
    for i, ch in enumerate(text):
        if ch == " ":
            out.append(" ")
            continue
        t = i / max(1, total - 1)
        r = int(c0[0] + (c1[0] - c0[0]) * t)
        g = int(c0[1] + (c1[1] - c0[1]) * t)
        b = int(c0[2] + (c1[2] - c0[2]) * t)
        out.append("\033[38;2;{};{};{}m{}".format(r, g, b, ch))
    out.append(RESET)
    return "".join(out)

class Cell:
    def __init__(self):
        self.buf = ""
        self.w = 0

    def text(self, s, rgb=None, bold=False):
        self.buf += colorize(s, rgb, bold)
        self.w += len(s)
        return self

    def raw(self, styled, vis):
        self.buf += styled
        self.w += vis
        return self

    def render(self, width, align="left"):
        pad = max(0, width - self.w)
        if align == "right":
            return " " * pad + self.buf
        if align == "center":
            left = pad // 2
            return " " * left + self.buf + " " * (pad - left)
        return self.buf + " " * pad


def bar(value, width, rgb):
    value = max(0.0, min(1.0, value))
    fill = int(round(value * width))
    styled = colorize("█" * fill, rgb) + colorize("░" * (width - fill), GREY)
    return styled, width


def sparkline(vals, n=14):
    vals = vals[-n:]
    if not vals:
        return ""
    mx = max(vals) or 1
    return "".join(SPARKS[min(7, int(v / mx * 7))] for v in vals)


def trunc(s, w):
    if w <= 0:
        return ""
    return s if len(s) <= w else s[: max(0, w - 1)] + "…"

DOT = [[0x01, 0x02, 0x04, 0x40], [0x08, 0x10, 0x20, 0x80]]


def braille_plot(series, plot_w, plot_h):
    """Plot `series` (values in 0..1) onto a plot_w x plot_h grid of braille cells."""
    w_px = max(2, plot_w * 2)
    h_px = max(4, plot_h * 4)
    lit = [[False] * w_px for _ in range(h_px)]
    n = len(series)

    def to_px(i, v):
        x = 0 if n <= 1 else int(round(i * (w_px - 1) / (n - 1)))
        v = max(0.0, min(1.0, v))
        y = int(round((1.0 - v) * (h_px - 1)))  # value 1.0 -> top row
        return x, y

    pts = [to_px(i, series[i]) for i in range(n)]
    if n == 1:
        x, y = pts[0]
        lit[y][x] = True
    for a in range(n - 1):
        x0, y0 = pts[a]
        x1, y1 = pts[a + 1]
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        sx = 1 if x0 <= x1 else -1
        sy = 1 if y0 <= y1 else -1
        err = dx - dy
        x, y = x0, y0
        while True:  # Bresenham line so segments connect smoothly
            lit[y][x] = True
            if x == x1 and y == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy

    rows = []
    for cy in range(plot_h):
        chars = []
        for cx in range(plot_w):
            bits = 0
            for ix in range(2):
                for iy in range(4):
                    py, pxc = cy * 4 + iy, cx * 2 + ix
                    if py < h_px and pxc < w_px and lit[py][pxc]:
                        bits |= DOT[ix][iy]
            chars.append(chr(0x2800 + bits) if bits else " ")
        rows.append("".join(chars))
    return rows


FONT = {
    "A": ["█████╗ ", "██╔══██╗", "███████║", "██╔══██║", "██║  ██║", "╚═╝  ╚═╝"],
    "D": ["██████╗ ", "██╔══██╗", "██║  ██║", "██║  ██║", "██████╔╝", "╚═════╝ "],
    "V": ["██╗   ██╗", "██║   ██║", "██║   ██║", "╚██╗ ██╔╝", " ╚████╔╝ ", "  ╚═══╝  "],
    "E": ["███████╗", "██╔════╝", "█████╗  ", "██╔══╝  ", "███████╗", "╚══════╝"],
    "R": ["██████╗ ", "██╔══██╗", "██████╔╝", "██╔══██╗", "██║  ██║", "╚═╝  ╚═╝"],
    "S": ["███████╗", "██╔════╝", "╚█████╗ ", " ╚═══██╗", "██████╔╝", "╚═════╝ "],
    "Y": ["██╗   ██╗", "╚██╗ ██╔╝", " ╚████╔╝ ", "  ╚██╔╝  ", "   ██║   ", "   ╚═╝   "],
    "N": ["███╗   ██╗", "████╗  ██║", "██╔██╗ ██║", "██║╚██╗██║", "██║ ╚████║", "╚═╝  ╚═══╝"],
    "M": ["███╗   ███╗", "████╗ ████║", "██╔████╔██║", "██║╚██╔╝██║", "██║ ╚═╝ ██║", "╚═╝     ╚═╝"],
    " ": ["   "] * 6,
}


def _normalize(glyph):
    w = max(len(r) for r in glyph)
    return [r.ljust(w) for r in glyph]


def banner_block(title):
    rows = [""] * 6
    for ch in title:
        glyph = _normalize(FONT.get(ch.upper(), FONT[" "]))
        for i in range(6):
            rows[i] += glyph[i]
    return rows


def compose_banner(width):
    rows = banner_block(TITLE)
    bw = max(len(r) for r in rows)
    rows = [r.ljust(bw) for r in rows]
    if bw > width:  # narrow-terminal fallback
        plain = " ".join(TITLE)
        pad = max(0, width - len(plain))
        left = pad // 2
        return ["", " " * left + colorize(plain, CYAN, bold=True) + " " * (pad - left), ""]
    margin = (width - bw) // 2
    return [" " * margin + grad(r, CYAN, PURPLE, bw) for r in rows]


def center_line(s, width, rgb=None, bold=False):
    s = s[:width]
    pad = width - len(s)
    left = pad // 2
    return " " * left + colorize(s, rgb, bold) + " " * (pad - left)


def panel(title, cells, panel_w, body_h):
    inner = panel_w - 4
    fillers = max(0, panel_w - 5 - len(title))
    top = colorize("╭─ ", BORDER) + colorize(title, WHITE, bold=True) + colorize(" " + "─" * fillers + "╮", BORDER)
    lines = [top]
    rows = list(cells) + [Cell() for _ in range(max(0, body_h - len(cells)))]
    for c in rows[:body_h]:
        lines.append(colorize("│ ", BORDER) + c.render(inner) + colorize(" │", BORDER))
    lines.append(colorize("╰" + "─" * (panel_w - 2) + "╯", BORDER))
    return lines


def mutant_cells(st, panel_w):
    inner = panel_w - 4
    id_w = 22
    desc_w = inner - id_w - 2
    cells = []
    for m in st["mutants"]:
        c = Cell()
        mid = trunc(m["id"], id_w - 1).ljust(id_w)
        if m["status"] == "killed":
            c.text("✓ ", GREEN, bold=True)
            c.text(mid, GREY)
            c.text(trunc(m["desc"], desc_w), GREY)
        else:
            dot_col = YELLOW if m.get("flash") else RED
            c.text("● ", dot_col, bold=True)
            c.text(mid, WHITE if not m.get("flash") else YELLOW, bold=True)
            c.text(trunc(m["desc"], desc_w), GREY)
        cells.append(c)
    return cells


def telemetry_cells(st, panel_w):
    inner = panel_w - 4
    LBL = 10
    cells = []

    def row(label, build):
        c = Cell()
        c.text(label.ljust(LBL), GREY)
        build(c)
        cells.append(c)

    row("iter", lambda c: c.text("{:>2} / {}".format(st["iteration"], st["max_iter"]), WHITE, bold=True))

    def kr(c):
        v = st["kill_rate"]
        col = GREEN if v >= 0.8 else (YELLOW if v >= 0.4 else RED)
        styled, vis = bar(v, max(8, inner - LBL - 6), col)
        c.raw(styled, vis)
        c.text(" {:>3}%".format(int(round(v * 100))), col, bold=True)

    row("kill rate", kr)
    row("killed", lambda c: c.text("{} ".format(st["killed"]), GREEN, bold=True).text("/ {} mutants".format(st["total"]), GREY))

    def tok(c):
        c.text("{:,}".format(st["tokens"]), YELLOW, bold=True)
        sp = sparkline(st["token_history"])
        if sp:
            c.text("  " + sp, ORANGE)

    row("tokens", tok)
    # The two-tier story, made explicit for the judges: who invents the bugs vs. who
    # writes the tests. Show the bare model name (drop the provider prefix).
    row("adversary", lambda c: c.text(trunc(st["strategy_model"].split("/")[-1], inner - LBL), CYAN, bold=True))
    row("defender", lambda c: c.text(trunc(st["bulk_model"].split("/")[-1], inner - LBL), PURPLE, bold=True))

    def status(c):
        if st.get("plateau"):
            c.text("■ plateau — converged", GREEN, bold=True)
        elif st.get("done"):
            c.text("★ run complete", GREEN, bold=True)
        else:
            c.text(SPIN[st["spin"] % len(SPIN)] + " ", CYAN, bold=True).text(st["status"], CYAN)

    row("status", status)
    return cells


EVENT_STYLE = {
    "kill": ("✓", GREEN),
    "info": ("•", CYAN),
    "gen": ("✎", YELLOW),
    "run": ("▶", ORANGE),
    "warn": ("!", ORANGE),
    "done": ("★", GREEN),
}


def event_cells(st, panel_w, body_h):
    inner = panel_w - 4
    cells = []
    for kind, msg in st["events"][-body_h:]:
        icon, col = EVENT_STYLE.get(kind, ("•", GREY))
        c = Cell()
        c.text(icon + " ", col, bold=True)
        c.text(trunc(msg, inner - 2), WHITE if kind in ("kill", "done") else GREY)
        cells.append(c)
    return cells


CHART_H = 20


def convergence_cells(st, panel_w):
    inner = panel_w - 4
    gutter = 5  # 4-char y label + 1 axis char
    plot_w = max(8, inner - gutter)
    series = st["kill_series"]

    if not series:
        c = Cell()
        c.text("awaiting first iteration…", GREY)
        return [c] + [Cell() for _ in range(CHART_H + 1)]

    rows = braille_plot(series, plot_w, CHART_H)
    labels = {}
    for frac in (1.0, 0.75, 0.5, 0.25, 0.0):  # gridline labels spread down the axis
        labels[int(round((1 - frac) * (CHART_H - 1)))] = "{:>3.0f}%".format(frac * 100)
    cells = []
    for r, line in enumerate(rows):
        c = Cell()
        c.text(labels.get(r, "").rjust(4), GREY)
        c.text("┤", BORDER)
        v = 1 - r / (CHART_H - 1)  # value represented by this row's height
        col = GREEN if v >= 0.8 else (YELLOW if v >= 0.4 else (ORANGE if v >= 0.2 else RED))
        colored = "".join(colorize(ch, col, bold=True) if ch != " " else " " for ch in line)
        c.raw(colored, len(line))
        cells.append(c)

    axis = Cell()
    axis.text("    ", GREY).text("└" + "─" * plot_w, BORDER)
    cells.append(axis)

    n = len(series)
    left_s, right_s = "1", "iter {}".format(n)
    mid = max(1, plot_w - len(left_s) - len(right_s))
    xlab = Cell()
    xlab.text(trunc("     " + left_s + " " * mid + right_s, inner), GREY)
    cells.append(xlab)
    return cells


TOP_MARGIN = 2  # blank lines above the banner so it isn't flush against the prompt


def function_cells(st, panel_w):
    """One row per tracked function: status, name, kill-rate bar, killed/total."""
    inner = panel_w - 4
    name_w = min(30, max(16, inner - 18))
    cells = []
    for i, f in enumerate(st["functions"]):
        c = Cell()
        if f["done"]:
            c.text("✓ ", GREEN, bold=True)
        elif i == st.get("active", -1):
            c.text(SPIN[st["spin"] % len(SPIN)] + " ", CYAN, bold=True)
        else:
            c.text("· ", GREY)
        active = (i == st.get("active", -1))
        c.text(trunc(f["name"], name_w).ljust(name_w), WHITE if active or f["done"] else GREY, bold=active)
        v = f["kill_rate"]
        col = GREEN if v >= 0.8 else (YELLOW if v >= 0.4 else (ORANGE if v > 0 else GREY))
        styled, vis = bar(v, max(6, inner - name_w - 9), col)
        c.raw(styled, vis)
        c.text(" {:>2}/{:<2}".format(f["killed"], f["total"]), col, bold=True)
        cells.append(c)
    return cells


def repo_telemetry_cells(st, panel_w):
    inner = panel_w - 4
    LBL = 12
    cells = []

    def row(label, build):
        c = Cell()
        c.text(label.ljust(LBL), GREY)
        build(c)
        cells.append(c)

    row("functions", lambda c: c.text("{} / {}".format(st["done_count"], len(st["functions"])), WHITE, bold=True))

    def kr(c):
        v = st["kill_rate"]
        col = GREEN if v >= 0.8 else (YELLOW if v >= 0.4 else RED)
        styled, vis = bar(v, max(8, inner - LBL - 6), col)
        c.raw(styled, vis)
        c.text(" {:>3}%".format(int(round(v * 100))), col, bold=True)

    row("repo kill", kr)
    row("bugs caught", lambda c: c.text("{} ".format(st["killed"]), GREEN, bold=True).text("/ {} across repo".format(st["total"]), GREY))

    def tok(c):
        c.text("{:,}".format(st["tokens"]), YELLOW, bold=True)
        sp = sparkline(st["token_history"])
        if sp:
            c.text("  " + sp, ORANGE)

    row("tokens", tok)
    row("adversary", lambda c: c.text(trunc(st["strategy_model"].split("/")[-1], inner - LBL), CYAN, bold=True))
    row("defender", lambda c: c.text(trunc(st["bulk_model"].split("/")[-1], inner - LBL), PURPLE, bold=True))

    def status(c):
        if st.get("done"):
            c.text("★ repo hardened", GREEN, bold=True)
        else:
            c.text(SPIN[st["spin"] % len(SPIN)] + " ", CYAN, bold=True).text(st.get("status", ""), CYAN)

    row("status", status)
    return cells


def render_repo(st):
    W = st["W"]
    out = ["" for _ in range(TOP_MARGIN)]
    out += compose_banner(W)
    out.append(center_line("repo-wide hardening arena — {} functions tracked".format(len(st["functions"])), W, GREY))
    out.append("")

    gap = 3
    left_w = int((W - gap) * 0.60)
    right_w = W - gap - left_w
    body_h = max(len(st["functions"]), 7)

    left = panel("FUNCTIONS  ({}/{} hardened)".format(st["done_count"], len(st["functions"])), function_cells(st, left_w), left_w, body_h)
    right = panel("TELEMETRY", repo_telemetry_cells(st, right_w), right_w, body_h)
    for a, b in zip(left, right):
        out.append(a + " " * gap + b)

    out.append("")
    out += panel("EVENT LOG", event_cells(st, W, 5), W, 5)
    out.append("")
    out += panel("CONVERGENCE  (repo-wide kill rate over the sweep)", convergence_cells(st, W), W, CHART_H + 2)
    out.append(center_line("Ctrl-C to quit", W, GREY))
    return out


def render(st):
    if st.get("mode") == "repo":
        return render_repo(st)
    W = st["W"]
    out = ["" for _ in range(TOP_MARGIN)]
    out += compose_banner(W)
    out.append(center_line("adversarial test-generation arena", W, GREY))
    out.append("")

    gap = 3
    # give the mutants panel the larger share — it carries the long descriptions
    left_w = int((W - gap) * 0.60)
    right_w = W - gap - left_w
    body_h = max(len(st["mutants"]), 7)

    left = panel("MUTANTS  ({}/{} killed)".format(st["killed"], st["total"]), mutant_cells(st, left_w), left_w, body_h)
    right = panel("TELEMETRY", telemetry_cells(st, right_w), right_w, body_h)
    for a, b in zip(left, right):
        out.append(a + " " * gap + b)

    out.append("")
    out += panel("EVENT LOG", event_cells(st, W, 5), W, 5)
    out.append("")
    out += panel("CONVERGENCE  (kill rate vs. iteration)", convergence_cells(st, W), W, CHART_H + 2)
    out.append(center_line("Ctrl-C to quit", W, GREY))
    return out

class Screen:
    def __init__(self, live, snapshot):
        self.live = live and not snapshot
        self.snapshot = snapshot
        self._primed = False

    def __enter__(self):
        if self.live:
            # Alt screen buffer has no scrollback, so overflow clips instead of pushing
            # earlier frames into history (which is what makes selections drift upward).
            sys.stdout.write("\033[?1049h\033[?25l\033[2J\033[H")
            sys.stdout.flush()
        return self

    def __exit__(self, *exc):
        if self.live:
            sys.stdout.write("\033[?25h\033[?1049l")
            sys.stdout.flush()

    def commit(self, st):
        lines = render(st)
        if self.live:
            sys.stdout.write("\033[H")
            sys.stdout.write("\n".join(line + "\033[K" for line in lines))
            sys.stdout.write("\033[J")
            sys.stdout.flush()
        else:
            if self._primed:
                sys.stdout.write("\n")
            sys.stdout.write("\n".join(lines) + "\n")
            sys.stdout.flush()
            self._primed = True

    def hold(self):
        """Keep the final frame up until the user quits.

        In live mode the arena draws on the alt-screen buffer, which __exit__ tears down
        the instant the `with` block ends — so without this the demo appears to close
        itself the moment it finishes. The footer already says 'Ctrl-C to quit', so we
        wait for exactly that. No-op for snapshot/non-tty output, which persists anyway.
        """
        if not self.live:
            return
        try:
            while True:
                time.sleep(0.25)
        except KeyboardInterrupt:
            pass

SIM_TESTS = [
    ("M1_no_sort",
     "def test_unsorted_input_merges(merge_intervals):\n"
     "    assert merge_intervals([[2, 6], [1, 3]]) == [[1, 6]]\n"),
    ("M2_strict_overlap",
     "def test_touching_intervals_merge(merge_intervals):\n"
     "    assert merge_intervals([[1, 2], [2, 3]]) == [[1, 3]]\n"),
    ("M3_overwrite_end",
     "def test_nested_interval_keeps_max_end(merge_intervals):\n"
     "    assert merge_intervals([[1, 5], [2, 3]]) == [[1, 5]]\n"),
    ("M4_drop_last",
     "def test_last_interval_is_kept(merge_intervals):\n"
     "    assert merge_intervals([[1, 2]]) == [[1, 2]]\n"),
    ("M5_empty_returns_none",
     "def test_empty_returns_empty_list(merge_intervals):\n"
     "    assert merge_intervals([]) == []\n"),
]
SIM_SMOKE = "def test_smoke(merge_intervals):\n    assert merge_intervals([[1, 3], [2, 6]]) == [[1, 6]]\n"


def make_sim_complete(llm):
    import random

    rng = random.Random(7)

    def _complete(prompt, role="strategy", **kwargs):
        body = SIM_SMOKE
        for mid, test in SIM_TESTS:  # escalate to the first surviving mutant
            if mid in prompt:
                body = test
                break
        text = "```python\n" + body + "```"
        tin = max(1, len(prompt) // 4) + rng.randint(40, 160)
        tout = max(20, len(body) // 4) + rng.randint(40, 160)
        return {"text": text, "model": llm.resolve_model(role), "tokens": {"in": tin, "out": tout}}

    return _complete

def run(opts):
    import llm
    from generator import generate_test
    from harness import JsonlLogger, compute_kill_rate, is_plateau, make_log_entry, run_baseline
    import adversary
    from main import MUTANT_ROUNDS, MUTANTS_PER_ROUND, ROLE_ORDER, _get_runner, resolve_target

    # The offline simulator only knows the built-in fixture — it returns canned
    # merge_intervals tests for ANY prompt. So it's only valid when no real repo is
    # targeted; running discovery/harden of a real repo through it just feeds garbage
    # to mutant-gen. When a repo is given we use real LLM calls regardless of --live.
    targeting_repo = bool(opts.target.get("repo"))
    if not opts.live and not targeting_repo:
        llm.complete = make_sim_complete(llm)
    elif not opts.live and targeting_repo:
        print("[demo] real repo target -> using live LLM calls (the offline simulation only "
              "knows the built-in fixture). For a fast, no-token showcase of a finished run, "
              "run main.py once then:  python3 demo.py --replay <run_log.jsonl>")

    # repo without a function -> discover the first eligible target to visualize.
    if opts.target.get("repo") and not opts.target.get("function"):
        import discover
        n = int(opts.target.get("mutants", "5"))
        found = discover.discover_targets(opts.target["repo"], mutants_per=n, max_targets=1, only_file=opts.target.get("file"))
        if not found:
            raise SystemExit(
                "no targets with valid mutants in {} — see the discover log above: either "
                "nothing passed the import/eligibility gate, or mutant generation failed for "
                "every candidate attempted (the ✗ lines).".format(opts.target["repo"]))
        rel, t = found[0]
        opts.target.setdefault("file", rel)
        opts.target["function"] = t.function_name
        REFERENCE_SRC, MUTANTS, language, function_name = t.reference_src, t.mutants, t.language, t.function_name
        runner, test_import_path, context = None, None, t.context
    else:
        REFERENCE_SRC, MUTANTS, language, function_name, runner, test_import_path = resolve_target(opts.target)
        context = None
    base_run_and_check = _get_runner(language, runner)
    # Not-self-contained targets carry a package import context; bind it so run_and_check
    # rebuilds the package sandbox (standalone targets keep the plain signature).
    run_and_check = functools.partial(base_run_and_check, context=context) if context else base_run_and_check

    def gen_fn(ref, surviving, role="bulk"):
        return generate_test(ref, surviving, role=role, language=language,
                             function_name=function_name, test_import_path=test_import_path)

    term_w = shutil.get_terminal_size(fallback=(96, 30)).columns
    W = opts.width or min(max(term_w, 76), 160)

    st = {
        "W": W,
        "mutants": [{"id": m["id"], "desc": m.get("description", ""), "status": "alive", "flash": False} for m in MUTANTS],
        "iteration": 0,
        "max_iter": opts.max_iter,
        "kill_rate": 0.0,
        "killed": 0,
        "total": len(MUTANTS),
        "tokens": 0,
        "token_history": [],
        "kill_series": [],
        "status": "warming up",
        "spin": 0,
        "strategy_model": llm.ROUTES.get("strategy", "?"),
        "bulk_model": llm.ROUTES.get("bulk", "?"),
        "events": [("info", "arena initialized, {} mutants loaded".format(len(MUTANTS)))],
        "log": opts.log,
    }
    if opts.target.get("repo"):
        st["events"].append(("info", "hardening {}::{}".format(opts.target.get("file", "?"), function_name)))

    delay = opts.delay
    screen = Screen(live=sys.stdout.isatty(), snapshot=opts.snapshot)
    by_id = {m["id"]: m for m in st["mutants"]}

    def spin_during(label, work):
        """Run blocking `work()` in a thread while animating the spinner."""
        st["status"] = label
        out, err = [], []

        def worker():
            try:
                out.append(work())
            except Exception as exc:  # surface in the main thread
                err.append(exc)

        t = threading.Thread(target=worker, daemon=True)
        t.start()
        if screen.live:
            while t.is_alive():
                st["spin"] += 1
                screen.commit(st)
                time.sleep(0.08)
        t.join()
        if err:
            raise err[0]
        if not screen.live:
            screen.commit(st)
        return out[0]

    with screen:
        screen.commit(st)
        if screen.live:
            time.sleep(0.6)

        logger = JsonlLogger(opts.log)
        total = len(MUTANTS)

        baseline = spin_during(
            "computing cold-start baseline",
            lambda: run_baseline(REFERENCE_SRC, MUTANTS, gen_fn, run_and_check),
        )
        st["events"].append(("info", "baseline kill_rate={:.2f}  ({} tokens, cold start)".format(baseline["kill_rate"], baseline["cumulative_tokens"])))
        screen.commit(st)

        surviving = list(MUTANTS)
        killed_total = set()
        kill_rates = []
        suite_sources = []
        existing_ids = set(m["id"] for m in MUTANTS)
        mutant_round = 0
        role_idx = 0

        for iteration in range(1, opts.max_iter + 1):
            st["iteration"] = iteration

            role = ROLE_ORDER[role_idx]
            st["tier"] = role
            tier_name = "smart" if role == "strategy" else "fast"
            active_model = st["strategy_model"] if role == "strategy" else st["bulk_model"]
            gen = spin_during(
                "defender writing a test",
                lambda: gen_fn(REFERENCE_SRC, surviving, role=role),
            )
            delta = gen["tokens"]["in"] + gen["tokens"]["out"]
            st["tokens"] += delta
            st["token_history"].append(delta)
            st["events"].append(("gen", "iter {}: synthesized test  (+{:,} tokens)".format(iteration, delta)))

            result = spin_during(
                "executing test against {} survivors".format(len(surviving)),
                lambda: run_and_check(gen["test_src"], REFERENCE_SRC, surviving),
            )
            killed_this_round = result["killed_mutant_ids"] if result["reference_passed"] else []
            if result["reference_passed"] and killed_this_round:
                suite_sources.append(gen["test_src"])

            for mid in killed_this_round:
                if mid in killed_total:
                    continue
                killed_total.add(mid)
                m = by_id.get(mid)
                if m:
                    m["status"] = "killed"
                    m["flash"] = True
                st["killed"] = len(killed_total)
                st["events"].append(("kill", "iter {}: KILLED {}".format(iteration, mid)))
                screen.commit(st)
                if screen.live:
                    time.sleep(0.18)
                    if m:
                        m["flash"] = False

            surviving = [m for m in surviving if m["id"] not in killed_total]

            st["kill_rate"] = compute_kill_rate(len(killed_total), total)
            kill_rates.append(st["kill_rate"])
            st["kill_series"].append(st["kill_rate"])
            if not killed_this_round:
                st["events"].append(("info", "iter {}: no new kills".format(iteration)))

            logger.append(make_log_entry(iteration, st["tokens"], st["kill_rate"], killed_this_round))
            st["status"] = "iteration {} complete".format(iteration)
            screen.commit(st)
            if screen.live:
                time.sleep(delay)

            # WAVE CLEARED: suite kills every current mutant -> the adversary invents new
            # bugs the suite misses. The mutant board GROWS and the kill rate dips, then
            # the defender climbs back. This is the co-evolution arms race on screen.
            if not surviving:
                if mutant_round >= MUTANT_ROUNDS:
                    st["plateau"] = True
                    st["events"].append(("done", "all waves cleared within budget ({} rounds)".format(MUTANT_ROUNDS)))
                    screen.commit(st)
                    break
                mutant_round += 1
                adv = spin_during(
                    "adversary inventing bugs the suite misses (round {})".format(mutant_round),
                    lambda: adversary.generate_surviving_mutants(
                        REFERENCE_SRC, function_name, language, suite_sources, run_and_check,
                        n=MUTANTS_PER_ROUND, existing_ids=existing_ids, round_idx=mutant_round, role="strategy",
                        context=context),
                )
                st["tokens"] += adv["tokens"]
                st["token_history"].append(adv["tokens"])
                if not adv["mutants"]:
                    st["plateau"] = True
                    st["events"].append(("done", "adversary defeated at round {} — suite is robust".format(mutant_round)))
                    screen.commit(st)
                    break
                for m in adv["mutants"]:
                    panel = {"id": m["id"], "desc": m.get("description", ""), "status": "alive", "flash": True}
                    st["mutants"].append(panel)
                    by_id[m["id"]] = panel
                surviving = list(adv["mutants"])
                total += len(adv["mutants"])
                st["total"] = total
                kill_rates = []
                role_idx = 0          # fresh wave: start cheap again
                st["kill_rate"] = compute_kill_rate(len(killed_total), total)
                st["kill_series"].append(st["kill_rate"])
                st["events"].append(("warn", "adversary round {}: +{} new bugs the suite missed".format(mutant_round, len(adv["mutants"]))))
                screen.commit(st)
                if screen.live:
                    time.sleep(max(delay, 0.5))
                    for m in adv["mutants"]:
                        by_id[m["id"]]["flash"] = False
                continue

            if is_plateau(kill_rates):
                # Don't quit — escalate cheap->smart, then stop only if the strongest
                # tier also stalls. This is the moment the curve jumps in the graph.
                if role_idx + 1 < len(ROLE_ORDER):
                    role_idx += 1
                    kill_rates = []
                    st["events"].append(("warn", "plateau on {} ({} surviving) -> escalating to {}".format(
                        ROLE_ORDER[role_idx - 1], len(surviving), ROLE_ORDER[role_idx])))
                    screen.commit(st)
                    if screen.live:
                        time.sleep(max(delay, 0.4))
                    continue
                st["plateau"] = True
                st["events"].append(("done", "plateau on strongest tier — {} mutant(s) unkilled".format(len(surviving))))
                screen.commit(st)
                break

        st["done"] = True
        st["events"].append(("done", "final kill_rate={:.0%} over {} mutants  /  {:,} tokens".format(st["kill_rate"], total, st["tokens"])))
        screen.commit(st)
        screen.hold()

    import report
    meta = {
        "repo": opts.target.get("repo", "(built-in fixture)"),
        "file": opts.target.get("file", "-"),
        "function": function_name or opts.target.get("function", "-"),
        "language": language,
        "strategy_model": st["strategy_model"],
        "bulk_model": st["bulk_model"],
        "total_mutants": total,
        "surviving": surviving,
        "mutant_rounds": mutant_round,
        "killed_total": len(killed_total),
    }
    report_path = report.write_report(meta, logger.entries, suite_sources, baseline=baseline);
    st["events"].append(("done", "report written to {}".format(report_path)));
    print("report at {}".format(report_path));

def _is_metric(entry):
    """An iteration data-point — exactly what report._metric_entries plots, so the replay
    graph is identical to main.py's report graph. Matches BOTH schemas: the structured
    `iteration_completed`/`run_finished` events and the flat `make_log_entry` lines."""
    return "kill_rate" in entry and entry.get("event") in (None, "iteration_completed", "run_finished")


def replay(opts):
    """DEMO MODE: re-animate a real main.py run from its jsonl log — no LLM calls.

    State is reconstructed from the log, so the convergence curve here IS the data main.py's
    report plots: replay is the guarantee the demo and the full run show the identical curve.
    Works on both the structured-event log and the flat make_log_entry log.
    """
    import llm

    with open(opts.replay) as handle:
        entries = [json.loads(line) for line in handle if line.strip()]

    started = next((e for e in entries if e.get("event") == "run_started"), {})
    target = started.get("target", {}) or {}
    # Descriptions, when the log carries structured mutant records (richer panel).
    desc_by_id = {}
    for e in entries:
        for m in (e.get("mutants") or []) + (e.get("surviving_mutants") or []):
            if m.get("id"):
                desc_by_id.setdefault(m["id"], m.get("description", ""))
    max_iter = max([e.get("iteration", 0) for e in entries if e.get("iteration") is not None] + [1])

    term_w = shutil.get_terminal_size(fallback=(96, 30)).columns
    W = opts.width or min(max(term_w, 76), 160)

    st = {
        "W": W,
        "mutants": [],
        "iteration": 0,
        "max_iter": max_iter,
        "kill_rate": 0.0,
        "killed": 0,
        "total": 0,
        "tokens": 0,
        "token_history": [],
        "kill_series": [],
        "status": "replaying {}".format(target.get("label") or target.get("function") or "run"),
        "spin": 0,
        "strategy_model": llm.ROUTES.get("strategy", "?"),
        "bulk_model": llm.ROUTES.get("bulk", "?"),
        "events": [("info", "REPLAY of {} ({} iterations)".format(opts.replay, max_iter))],
        "log": None,
    }
    if target.get("label") or target.get("function"):
        st["events"].append(("info", "target {}".format(target.get("label") or target.get("function"))))

    killed_ids = []          # real ids, accumulated in kill order
    screen = Screen(live=sys.stdout.isatty(), snapshot=opts.snapshot)

    def rebuild_panel(flash_ids=()):
        # The board = every killed mutant (named by its real id) + the surviving remainder.
        rows = []
        for kid in killed_ids:
            rows.append({"id": kid, "desc": desc_by_id.get(kid, ""), "status": "killed", "flash": kid in flash_ids})
        for k in range(max(0, st["total"] - len(killed_ids))):
            rows.append({"id": "surviving_bug_{}".format(k + 1), "desc": "bug the suite hasn't caught yet", "status": "alive", "flash": False})
        st["mutants"] = rows

    with screen:
        screen.commit(st)
        if screen.live:
            time.sleep(0.4)
        for e in entries:
            if not _is_metric(e):     # run_started / mutants_generated narration — skip
                continue
            if e.get("event") == "run_finished":
                st["kill_rate"] = e.get("kill_rate", st["kill_rate"])
                st["kill_series"].append(st["kill_rate"])    # report includes the run_finished point
                st["done"] = True
                stop = e.get("stop_reason", "")
                st["plateau"] = stop in ("adversary_defeated", "plateau", "defender_plateau", "rounds_exhausted")
                st["events"].append(("done", "final kill_rate={:.0%} — {} ({} mutants)".format(st["kill_rate"], stop or "done", st["total"])))
                screen.commit(st)
                if screen.live:
                    time.sleep(0.5)
                continue

            # An iteration data-point (flat line or iteration_completed event).
            prev_tokens = st["tokens"]
            st["iteration"] = e.get("iteration", st["iteration"] + 1)
            st["tokens"] = e.get("cumulative_tokens", prev_tokens)
            st["token_history"].append(max(0, st["tokens"] - prev_tokens))
            st["tier"] = e.get("tier")
            new_total = e.get("total_mutants", st["total"])
            if new_total > st["total"] and st["total"] > 0:    # a wave: the board grew
                st["events"].append(("warn", "adversary round {}: +{} new bugs the suite missed".format(
                    e.get("mutant_round", "?"), new_total - st["total"])))
            st["total"] = new_total
            killed_now = e.get("killed_this_round") or []
            for kid in killed_now:
                if kid not in killed_ids:
                    killed_ids.append(kid)
                st["events"].append(("kill", "iter {}: KILLED {}".format(st["iteration"], kid)))
            st["killed"] = e.get("killed_cumulative", len(killed_ids))
            st["kill_rate"] = e.get("kill_rate", st["kill_rate"])
            st["kill_series"].append(st["kill_rate"])          # identical to report's metric series
            st["status"] = "iter {} — {} tier".format(st["iteration"], e.get("tier", "?"))
            rebuild_panel(flash_ids=set(killed_now))
            screen.commit(st)
            if screen.live:
                if killed_now:
                    time.sleep(min(0.18, opts.delay))
                    rebuild_panel()
                time.sleep(opts.delay)
        screen.hold()


def _load_run(path):
    """Return (label, metric_entries) for one run log. Label comes from the structured
    run_started.target when present, else the file name (flat logs carry no target)."""
    import os
    with open(path) as handle:
        entries = [json.loads(line) for line in handle if line.strip()]
    started = next((e for e in entries if e.get("event") == "run_started"), {})
    target = (started.get("target") or {}) if started else {}
    label = target.get("label") or target.get("function") or os.path.splitext(os.path.basename(path))[0]
    return label, [e for e in entries if _is_metric(e)]


def replay_repo(opts, log_paths):
    """DEMO MODE (repo-wide): play EVERY tracked function as a live leaderboard with a
    single repo-wide kill-rate curve. Each function's run is replayed in turn; the board
    fills in and the aggregate curve climbs (dipping each time a new function — or an
    adversary wave — brings fresh uncaught bugs into the arena)."""
    import llm

    targets = []
    for path in log_paths:
        label, metrics = _load_run(path)
        if metrics:
            targets.append({"name": label, "metrics": metrics})
    if not targets:
        raise SystemExit("no usable run logs in {}".format(log_paths))

    term_w = shutil.get_terminal_size(fallback=(96, 30)).columns
    W = opts.width or min(max(term_w, 76), 160)
    functions = [{"name": t["name"], "kill_rate": 0.0, "killed": 0, "total": 0, "tokens": 0, "tier": "", "done": False} for t in targets]
    st = {
        "W": W,
        "mode": "repo",
        "functions": functions,
        "active": -1,
        "done_count": 0,
        "kill_rate": 0.0,
        "killed": 0,
        "total": 0,
        "tokens": 0,
        "token_history": [],
        "kill_series": [],
        "status": "starting repo sweep",
        "spin": 0,
        "strategy_model": llm.ROUTES.get("strategy", "?"),
        "bulk_model": llm.ROUTES.get("bulk", "?"),
        "events": [("info", "REPLAY repo sweep — {} functions tracked".format(len(functions)))],
    }

    def aggregate():
        st["killed"] = sum(f["killed"] for f in functions)
        st["total"] = sum(f["total"] for f in functions)
        st["tokens"] = sum(f["tokens"] for f in functions)
        st["kill_rate"] = st["killed"] / st["total"] if st["total"] else 0.0

    def short(name):
        return name.split("::")[-1]

    screen = Screen(live=sys.stdout.isatty(), snapshot=opts.snapshot)
    with screen:
        screen.commit(st)
        if screen.live:
            time.sleep(0.4)
        for i, t in enumerate(targets):
            st["active"] = i
            f = functions[i]
            st["events"].append(("info", "▶ hardening {}".format(short(t["name"]))))
            for e in t["metrics"]:
                if e.get("event") == "run_finished":
                    f["kill_rate"] = e.get("kill_rate", f["kill_rate"])
                    continue
                prev_tokens = f["tokens"]
                f["tier"] = e.get("tier", f["tier"])
                f["total"] = e.get("total_mutants", f["total"])
                f["killed"] = e.get("killed_cumulative", f["killed"])
                f["kill_rate"] = e.get("kill_rate", f["kill_rate"])
                f["tokens"] = e.get("cumulative_tokens", prev_tokens)
                for kid in (e.get("killed_this_round") or []):
                    st["events"].append(("kill", "{}: KILLED {}".format(short(t["name"]), kid)))
                aggregate()
                st["token_history"].append(max(0, f["tokens"] - prev_tokens))
                st["kill_series"].append(st["kill_rate"])
                st["status"] = "{} — iter {} ({} tier)".format(short(t["name"]), e.get("iteration", "?"), e.get("tier", "?"))
                screen.commit(st)
                if screen.live:
                    time.sleep(opts.delay)
            f["done"] = True
            st["done_count"] += 1
            aggregate()
            st["events"].append(("done", "✓ {} hardened: {}/{} bugs".format(short(t["name"]), f["killed"], f["total"])))
            screen.commit(st)
            if screen.live:
                time.sleep(max(opts.delay, 0.3))
        st["done"] = True
        st["events"].append(("done", "repo sweep complete — {} bugs caught across {} functions / {:,} tokens".format(
            st["killed"], len(functions), st["tokens"])))
        screen.commit(st)
        screen.hold()


SPEEDS = {"slow": 1.1, "normal": 0.6, "fast": 0.25}


def main():
    global USE_COLOR
    p = argparse.ArgumentParser(description="Adversarial Arena — live terminal kill-board.")
    p.add_argument("--live", action="store_true", help="use real LLM calls instead of the offline simulation")
    p.add_argument("--replay", nargs="+", metavar="LOG", default=None, help="DEMO MODE: speedrun previous main.py run(s). One file = that function; a directory or several files = repo-wide leaderboard of all functions.")
    p.add_argument("--speed", choices=list(SPEEDS), default=None, help="demo pacing (default: normal live, fast on --replay)")
    p.add_argument("--delay", type=float, default=None, help="seconds between iterations (overrides --speed)")
    p.add_argument("--snapshot", action="store_true", help="print settled frames instead of redrawing in place")
    p.add_argument("--no-color", action="store_true", help="disable ANSI color")
    p.add_argument("--width", type=int, default=None, help="force a render width")
    p.add_argument("--max-iter", type=int, default=25, help="maximum iterations (default: 25)")
    p.add_argument("--log", default="demo_run.jsonl", help="jsonl log path (default: demo_run.jsonl)")
    opts, extras = p.parse_known_args()

    # repo=/file=/function= survive as extras and select a real-repo target
    # (same resolution as main.py); with none given, the built-in fixture is used.
    opts.target = {}
    for arg in extras:
        if "=" in arg:
            key, _, value = arg.partition("=")
            opts.target[key.strip()] = value.strip()

    if opts.no_color:
        USE_COLOR = False
    speed = opts.speed or ("fast" if opts.replay else "normal")
    opts.delay = opts.delay if opts.delay is not None else SPEEDS[speed]

    # Expand --replay into a concrete list of log files (a dir -> its run_*.jsonl).
    replay_logs = None
    if opts.replay:
        import glob
        import os
        expanded = []
        for item in opts.replay:
            if os.path.isdir(item):
                expanded += sorted(glob.glob(os.path.join(item, "run_*.jsonl")))
            elif any(ch in item for ch in "*?["):
                expanded += sorted(glob.glob(item))
            else:
                expanded.append(item)
        replay_logs = [p for p in expanded if os.path.isfile(p)]
        if not replay_logs:
            raise SystemExit("no run logs matched {}".format(opts.replay))

    try:
        if replay_logs and len(replay_logs) > 1:
            replay_repo(opts, replay_logs)
        elif replay_logs:
            opts.replay = replay_logs[0]      # single-file replay expects a path string
            replay(opts)
        else:
            run(opts)
    except KeyboardInterrupt:
        sys.stdout.write("\033[?25h\n")
        sys.stdout.flush()
        print("interrupted.")
        sys.exit(130)


if __name__ == "__main__":
    main()
