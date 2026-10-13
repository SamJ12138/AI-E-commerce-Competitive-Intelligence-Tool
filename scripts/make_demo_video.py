#!/usr/bin/env python3
"""
make_demo_video.py - Render the README demo video (docs/demo.mp4, docs/demo.gif) from one real run
of the tool. Nothing is screen-recorded by hand: run the script again and the same three acts are
rendered from a new scan.

Act 1, terminal. `python main.py --sites sites.txt --lang en`, with sites.txt holding one store
(default https://www.allbirds.com), is run once. Its output is read from a pipe (rich is told it
writes to a 100x27 terminal) into an asciinema v2 recording, <work>/run/session.cast, which is
then replayed through a terminal emulator (pyte) and drawn frame by frame with Pillow. The typed
`cat sites.txt` and command line before the run are added by this script. The fetch phase (from
the first line main.py prints to "Generating reports") plays at 8x with an "8x" label; when the
act would still run 10 s or longer the factor doubles (16x, 32x, 64x) and the label says so.
After that, any pause longer than 0.4 s is cut to 0.4 s, and the last screen is held 1.5 s.
Act 2, report. <work>/run/output/business_report.md is rendered to HTML with an inline
stylesheet, opened in headless Chromium (Playwright) at 1280x720 with every network request
refused, and scrolled from the top to the pricing figures and then to the shipping and returns
terms, 1.5 s on each, one screenshot per frame. A report on two or more stores has a comparison
table, and the stops are that table; a one-store report has none, so the stops are the "Pricing"
finding and the store's "Key Metrics" list.
Act 3, closing card (2 s).

Each act is encoded to its own h264 file (1280x720, 30 fps) and the three are concatenated with
the ffmpeg binary that ships with imageio-ffmpeg. docs/demo.gif is made from the result with a
two-pass palette: 960 px wide at 10 fps, then 8 fps, then 800 px while it is over 5 MB; over 8 MB
is an error.

The run: main.py runs with its working directory set to <work>/run, so every path it prints is
relative (the script refuses to render a recording that contains a home-directory path). As in
scripts/real_corpus.py, the cloudscraper fallback is switched off in the launching process,
because real-site runs must not take that path; everything else is the default: robots.txt
respected, 1.5 s between requests, no --render-js.

Usage:
    python scripts/make_demo_video.py                # one scan of the store, then render
    python scripts/make_demo_video.py --reuse-run    # render again from <work>/run, no network
    python scripts/make_demo_video.py --site https://example.com --work some/dir

Needs requirements-dev.txt (pyte, Pillow, imageio-ffmpeg) and, once,
`python -m playwright install chromium`.
"""

import argparse
import codecs
import html as html_lib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path

import pyte
from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parent.parent

SIZE = (1280, 720)
FPS = 30
TERM_COLS, TERM_ROWS = 100, 27
PROMPT = "\x1b[32m$\x1b[0m "
COMMAND = "python main.py --sites sites.txt --lang en"
DEFAULT_SITE = "https://www.allbirds.com"
REPO_OWNER, REPO_NAME = "SamJ12138", "AI-E-commerce-Competitive-Intelligence-Tool"

ACT1_LIMIT = 10.0           # seconds; the terminal act must be shorter
SPEEDS = (8, 16, 32, 64)    # fetch-phase speed-up, the first that fits ACT1_LIMIT
MAX_GAP = 0.4               # longest pause kept, after the speed-up
HOLD_END = 1.5              # last terminal screen
FAST_START, FAST_END = "fast-start", "fast-end"
CARD_SECONDS = 2.0

MB = 1024 * 1024
GIF_TARGET, GIF_LIMIT = 5 * MB, 8 * MB
GIF_LADDER = ((10, 960), (8, 960), (8, 800))

# ------------------------------------------------------------------ terminal look

TERM_BG = (24, 26, 33)
TERM_FG = (220, 223, 228)
BAR_H, PAD_X, PAD_Y = 40, 24, 8
LABEL_BOX = (SIZE[0] - 140, 6, SIZE[0] - 16, 34)
LABEL_BG, LABEL_FG = (229, 160, 60), (24, 26, 33)
DOTS = ((236, 95, 90), (229, 190, 70), (98, 196, 98))
PALETTE = {
    "black": (60, 64, 72), "red": (224, 108, 117), "green": (152, 195, 121),
    "brown": (229, 192, 123), "blue": (97, 175, 239), "magenta": (198, 120, 221),
    "cyan": (86, 182, 194), "white": (220, 223, 228),
    "brightblack": (110, 116, 128), "brightred": (240, 135, 140), "brightgreen": (175, 215, 140),
    "brightbrown": (240, 210, 150), "brightblue": (130, 195, 250), "brightmagenta": (215, 150, 235),
    "brightcyan": (120, 205, 215), "brightwhite": (250, 250, 250),
}

MONO_FONTS = ("DejaVuSansMono.ttf", "consola.ttf", "CascadiaMono.ttf", "Menlo.ttc",
              "LiberationMono-Regular.ttf")
EMOJI_FONTS = ("seguiemj.ttf", "Apple Color Emoji.ttc")
SYMBOL_FONTS = ("seguisym.ttf", "DejaVuSans.ttf", "Symbola.ttf")
SANS_FONTS = ("segoeui.ttf", "DejaVuSans.ttf", "Helvetica.ttc", "Arial.ttf")
SANS_BOLD_FONTS = ("segoeuib.ttf", "DejaVuSans-Bold.ttf", "Helvetica.ttc", "Arial Bold.ttf")


class DemoError(RuntimeError):
    pass


def load_font(names, size, required=True):
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size) if required else None


# ------------------------------------------------------------------ cast files (asciinema v2)

def read_cast(path):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    events = [tuple(json.loads(line)) for line in lines[1:] if line.strip()]
    return header, [(float(t), code, data) for t, code, data in events]


def write_cast(path, header, events):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(header) + "\n")
        for t, code, data in events:
            fh.write(json.dumps([round(t, 6), code, data]) + "\n")


def retime(events, speed=8, max_gap=MAX_GAP):
    """Play the part between the fast-start and fast-end markers `speed` times faster, then cut
    every pause longer than `max_gap`. Returns the new events and the sped-up window (new times),
    or None when the recording has no markers."""
    marks = {data: t for t, code, data in events if code == "m"}
    fs, fe = marks.get(FAST_START), marks.get(FAST_END)
    out, prev, now = [], None, 0.0
    for t, code, data in events:
        if prev is not None:
            dt = t - prev
            inside = max(0.0, min(t, fe) - max(prev, fs)) if fs is not None and fe is not None else 0.0
            now += min(inside / speed + (dt - inside), max_gap)
        prev = t
        out.append((now, code, data))
    new_marks = {data: t for t, code, data in out if code == "m"}
    window = (new_marks[FAST_START], new_marks[FAST_END]) if FAST_START in new_marks and FAST_END in new_marks else None
    return out, window


def screen_text(events, cols, rows):
    screen = pyte.Screen(cols, rows)
    stream = pyte.Stream(screen)
    for _, code, data in events:
        if code == "o":
            stream.feed(data)
    return screen.display


def private_path_hits(text):
    """Home-directory paths in `text` (a recording must not show where it was made)."""
    home = str(Path.home())
    hits = [v for v in {home, home.replace("\\", "/")} if v and v.lower() in text.lower()]
    hits += re.findall(r"[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s]+", text, re.I)
    hits += re.findall("/" + "home" + r"/[^/\s]+|/Users/[^/\s]+", text)   # in pieces: tests/test_repo_hygiene.py
    return sorted(set(hits))


def check_no_private_paths(text):
    hits = private_path_hits(text)
    if hits:
        raise DemoError(f"the recording shows home-directory paths, refusing to render it: {hits}")


# ------------------------------------------------------------------ terminal frames

class TermPainter:
    """Draws a pyte screen onto a 1280x720 frame."""

    def __init__(self, cols, rows, size=SIZE):
        self.cols, self.rows, self.size = cols, rows, size
        avail_w, avail_h = size[0] - 2 * PAD_X, size[1] - BAR_H - 2 * PAD_Y
        for fs in range(30, 7, -1):
            font = load_font(MONO_FONTS, fs)
            adv, lh = font.getlength("M"), math.ceil(fs * 1.22)
            if cols * adv <= avail_w and rows * lh <= avail_h:
                break
        self.font, self.adv, self.lh, self.fs = font, adv, lh, fs
        ascent, descent = font.getmetrics()
        self.baseline = (lh - (ascent + descent)) / 2 + ascent
        self.left = (size[0] - cols * adv) / 2
        self.top = BAR_H + PAD_Y
        self.emoji = load_font(EMOJI_FONTS, round(fs * 0.85), required=False)
        self.symbol = load_font(SYMBOL_FONTS, fs, required=False)
        self.label_font = load_font(SANS_BOLD_FONTS, 18)
        self._glyph_cache = {}

    def _missing(self, font):
        key = (id(font), None)
        if key not in self._glyph_cache:
            self._glyph_cache[key] = self._bitmap(font, "\U0010fffd")
        return self._glyph_cache[key]

    @staticmethod
    def _bitmap(font, ch):
        img = Image.new("L", (96, 96))
        ImageDraw.Draw(img).text((16, 16), ch, font=font, fill=255)
        return img.tobytes()

    def has_glyph(self, font, ch):
        key = (id(font), ch)
        if key not in self._glyph_cache:
            self._glyph_cache[key] = ch.isspace() or self._bitmap(font, ch) != self._missing(font)
        return self._glyph_cache[key]

    def _font_for(self, ch, wide):
        if ord(ch) < 0x2000 or self.has_glyph(self.font, ch):
            return self.font, False
        order = (self.emoji, self.symbol) if wide else (self.symbol, self.emoji)
        for font in order:
            if font is not None and self.has_glyph(font, ch):
                return font, font is self.emoji
        return self.font, False

    @staticmethod
    def colour(name, bold, default):
        if name == "default":
            return default
        if re.fullmatch(r"[0-9a-fA-F]{6}", name):
            return tuple(int(name[i:i + 2], 16) for i in (0, 2, 4))
        if bold and not name.startswith("bright"):
            name = "bright" + name
        return PALETTE.get(name, default)

    def paint(self, screen, label=None):
        img = Image.new("RGB", self.size, TERM_BG)
        draw = ImageDraw.Draw(img)
        for i, c in enumerate(DOTS):
            draw.ellipse((PAD_X + i * 22, 14, PAD_X + i * 22 + 12, 26), fill=c)
        if label:
            draw.rounded_rectangle(LABEL_BOX, radius=8, fill=LABEL_BG)
            cx, cy = (LABEL_BOX[0] + LABEL_BOX[2]) / 2, (LABEL_BOX[1] + LABEL_BOX[3]) / 2
            draw.text((cx, cy), label, font=self.label_font, fill=LABEL_FG, anchor="mm")
        for y in range(self.rows):
            line = screen.buffer[y]
            row_top = self.top + y * self.lh
            x = 0
            while x < self.cols:
                char = line[x]
                ch = char.data
                if not ch or ch == " " and char.bg == "default" and not char.reverse:
                    x += 1
                    continue
                wide = x + 1 < self.cols and line[x + 1].data == ""
                fg = self.colour(char.fg, char.bold, TERM_FG)
                bg = self.colour(char.bg, False, TERM_BG)
                if char.reverse:
                    fg, bg = bg, fg
                cells = 2 if wide else 1
                left = self.left + x * self.adv
                if bg != TERM_BG:
                    draw.rectangle((left, row_top, left + cells * self.adv, row_top + self.lh - 1), fill=bg)
                font, colour_glyph = self._font_for(ch, wide)
                if colour_glyph:
                    draw.text((left + cells * self.adv / 2, row_top + self.lh / 2), ch, font=font,
                              anchor="mm", embedded_color=True)
                elif font is self.font:
                    draw.text((left, row_top + self.baseline), ch, font=font, fill=fg, anchor="ls")
                else:
                    draw.text((left + cells * self.adv / 2, row_top + self.lh / 2), ch, font=font,
                              fill=fg, anchor="mm")
                x += cells
        cur = screen.cursor
        if not cur.hidden and cur.y < self.rows and cur.x < self.cols:
            left, row_top = self.left + cur.x * self.adv, self.top + cur.y * self.lh
            draw.rectangle((left, row_top + 2, left + self.adv - 1, row_top + self.lh - 2), fill=TERM_FG)
        return img


def frame_count(end, hold, fps):
    return math.ceil(round((end + hold) * fps, 6))


def render_terminal_frames(events, cols, rows, fps=FPS, hold=HOLD_END, window=None, label=None,
                           watch=(), seen=None):
    """Yield one frame per 1/fps second. `seen[text]` collects the frames whose screen shows text."""
    screen = pyte.Screen(cols, rows)
    stream = pyte.Stream(screen)
    painter = TermPainter(cols, rows)
    out = [e for e in events if e[1] == "o"]
    end = events[-1][0] if events else 0.0
    n = frame_count(end, hold, fps)
    i, last, last_key = 0, None, None
    for k in range(n):
        t = k / fps
        fed = False
        while i < len(out) and (out[i][0] <= t + 1e-9 or k == n - 1):
            stream.feed(out[i][2])
            i, fed = i + 1, True
        show = bool(window and label and window[0] - 1e-9 <= t < window[1] - 1e-9)
        key = (show,)
        if fed or last is None or key != last_key:
            last, last_key = painter.paint(screen, label if show else None), key
            if seen is not None:
                text = "\n".join(screen.display)
                found = {w for w in watch if w in text}
        if seen is not None:
            for w in found:
                seen.setdefault(w, []).append(k)
        yield last


def cast_to_frames(path, fps=FPS, hold=HOLD_END, speed=8, max_gap=MAX_GAP, label=None):
    header, events = read_cast(path)
    events, window = retime(events, speed, max_gap)
    yield from render_terminal_frames(events, header["width"], header["height"], fps, hold, window,
                                      label or f"{speed}x")


def plan_terminal(events, limit=ACT1_LIMIT, hold=HOLD_END, speeds=SPEEDS):
    for speed in speeds:
        out, window = retime(events, speed, MAX_GAP)
        if frame_count(out[-1][0], hold, FPS) / FPS < limit:
            return speed, out, window
    raise DemoError(f"the terminal act is {out[-1][0] + hold:.1f} s even at {speeds[-1]}x")


# ------------------------------------------------------------------ the real run

BOOTSTRAP = (
    "import sys, runpy\n"
    "repo = sys.argv[1]\n"
    "sys.path.insert(0, repo)\n"
    "import rich.console\n"
    "rich.console.detect_legacy_windows = lambda: False\n"   # VT escape codes into the pipe
    "import modules.http_client as h\n"
    "h.CLOUDSCRAPER_AVAILABLE = False\n"
    "sys.argv = ['main.py'] + sys.argv[2:]\n"
    "runpy.run_path(repo + '/main.py', run_name='__main__')\n"
)
RUN_MARKER = ".make_demo_video"


def intro_events(sites_text, typing=0.035):
    """The typed part before the run: `cat sites.txt`, its content, and the command."""
    events, t = [(0.0, "o", PROMPT)], 0.4
    for ch in "cat sites.txt":
        events.append((t, "o", ch))
        t += typing
    t += 0.2
    events.append((t, "o", "\r\n" + sites_text.rstrip("\n").replace("\n", "\r\n") + "\r\n"))
    t += 0.4
    events.append((t, "o", PROMPT))
    t += 0.3
    for ch in COMMAND:
        events.append((t, "o", ch))
        t += typing
    t += 0.3
    events.append((t, "o", "\r\n"))
    return events, t


def capture_run(run_dir, site, cols=TERM_COLS, rows=TERM_ROWS):
    """Run main.py once in run_dir and record its output as an asciinema v2 cast."""
    if run_dir.exists():
        if not (run_dir / RUN_MARKER).exists():
            raise DemoError(f"{run_dir} exists and was not made by this script; choose another --work")
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    (run_dir / RUN_MARKER).write_text("made by scripts/make_demo_video.py\n", encoding="utf-8")
    sites_text = site + "\n"
    (run_dir / "sites.txt").write_text(sites_text, encoding="utf-8")

    env = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "PYTHONUTF8")}
    env.update(COLUMNS=str(cols), LINES=str(rows), TTY_COMPATIBLE="1", TTY_INTERACTIVE="1",
               PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1", ECI_LOG_DIR="logs", TERM="xterm-256color")
    intro, intro_end = intro_events(sites_text)
    started = time.time()
    t0 = time.monotonic()
    proc = subprocess.Popen([sys.executable, "-c", BOOTSTRAP, str(REPO), "--sites", "sites.txt", "--lang", "en"],
                            cwd=run_dir, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    chunks = []
    while True:
        data = proc.stdout.read1(65536)
        if not data:
            break
        text = decoder.decode(data)
        if text:
            chunks.append((time.monotonic() - t0, re.sub(r"(?<!\r)\n", "\r\n", text)))
    code = proc.wait()
    if code != 0 or not chunks:
        raise DemoError(f"main.py exited with {code}; output in {run_dir}")

    run = [(intro_end + t, "o", text) for t, text in chunks]
    fast_start = run[0][0]
    seen, fast_end = "", run[-1][0]
    for t, _, text in run:
        seen += text
        if "Generating reports" in seen:
            fast_end = t
            break
    events = intro + [(fast_start, "m", FAST_START)] + [e for e in run if e[0] < fast_end] + \
        [(fast_end, "m", FAST_END)] + [e for e in run if e[0] >= fast_end]
    header = {"version": 2, "width": cols, "height": rows, "timestamp": int(started),
              "title": COMMAND, "env": {"TERM": "xterm-256color"}}
    cast = run_dir / "session.cast"
    write_cast(cast, header, events)
    return cast


# ------------------------------------------------------------------ report -> HTML -> frames

CSS = """
html { scroll-behavior: auto; }
body { margin: 0; background: #ffffff; color: #1f2328;
       font: 21px/1.5 "Segoe UI", "DejaVu Sans", "Helvetica Neue", Arial, sans-serif; }
main { max-width: 1060px; margin: 0 auto; padding: 36px 48px 420px; }
h1 { font-size: 36px; margin: 0 0 14px; }
h2 { font-size: 28px; margin: 34px 0 12px; padding-bottom: 6px; border-bottom: 1px solid #d0d7de; }
h3 { font-size: 23px; margin: 26px 0 10px; }
p, ul, ol { margin: 8px 0; }
li { margin: 3px 0; }
a { color: #0969da; text-decoration: none; }
hr { border: 0; border-top: 1px solid #d0d7de; margin: 26px 0; }
table { border-collapse: collapse; margin: 12px 0; }
th, td { border: 1px solid #d0d7de; padding: 6px 14px; text-align: left; }
th { background: #f6f8fa; }
code { font-family: Consolas, "DejaVu Sans Mono", monospace; font-size: 0.9em;
       background: #f6f8fa; padding: 1px 5px; border-radius: 4px; }
"""


def _header_text(table):
    row = table.find("tr")
    return row.get_text(" ", strip=True) if row else ""


def _mark_stops(soup):
    """id="demo-sites" (the Sites Analyzed line), "demo-pricing" and "demo-terms" (shipping and returns)."""
    sites = soup.find(lambda el: el.name in ("p", "li") and re.search(r"sites analy[sz]ed", el.get_text(), re.I))
    if sites is not None:
        sites["id"] = "demo-sites"
    tables = soup.find_all("table")
    pricing = next((t for t in tables if "price" in _header_text(t).lower()), None)
    if pricing is None:
        pricing = soup.find(lambda el: el.name in ("p", "li") and re.match(r"\s*pric(ing|e range)", el.get_text(), re.I))
    if pricing is not None:
        pricing["id"] = "demo-pricing"
    terms = next((t for t in tables if t is not pricing
                  and re.search(r"shipping|returns", _header_text(t), re.I)), None)
    if terms is None:
        terms = soup.find(lambda el: el.name == "ul" and "Shipping" in el.get_text() and "Returns" in el.get_text())
    if terms is None and pricing is not None and pricing.name == "table":
        terms = pricing.find(lambda el: el.name == "th" and re.search(r"shipping|returns", el.get_text(), re.I))
    if terms is not None:
        terms["id"] = "demo-terms"


def markdown_to_html(md_text, title="business_report.md"):
    from bs4 import BeautifulSoup
    from markdown_it import MarkdownIt
    body = MarkdownIt("commonmark", {"html": False}).enable("table").render(md_text)
    page = (f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            f"<title>{html_lib.escape(title)}</title><style>{CSS}</style></head>"
            f"<body><main>{body}</main></body></html>")
    soup = BeautifulSoup(page, "html.parser")
    _mark_stops(soup)
    return str(soup)


def _ease(x):
    return x * x * (3 - 2 * x)


def scroll_positions(stops, fps=FPS, top_hold=2.5, move=1.25, hold=1.5):
    """Scroll offsets, one per frame: hold at the top, then ease to each stop and hold there."""
    ys = [0.0] * round(top_hold * fps)
    here = 0.0
    for target in stops:
        steps = round(move * fps)
        ys += [here + (target - here) * _ease((k + 1) / steps) for k in range(steps)]
        ys += [float(target)] * round(hold * fps)
        here = target
    return ys


GEOMETRY_JS = """() => {
  const out = {max: document.documentElement.scrollHeight - window.innerHeight, els: {}};
  for (const id of ["demo-sites", "demo-pricing", "demo-terms"]) {
    const el = document.getElementById(id);
    if (el) { const r = el.getBoundingClientRect();
              out.els[id] = [r.top + window.scrollY, r.bottom + window.scrollY]; }
  }
  return out;
}"""


def report_frames(html_path, fps=FPS, first_frame=0, seen=None):
    """Yield the scroll frames; `seen[id]` collects the (global) frames where each stop is fully visible."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": SIZE[0], "height": SIZE[1]}, device_scale_factor=1)
            page.route("**/*", lambda route: route.continue_() if route.request.url.startswith("file:")
                       else route.abort())
            page.goto(Path(html_path).resolve().as_uri())
            geo = page.evaluate(GEOMETRY_JS)
            missing = {"demo-pricing", "demo-terms"} - set(geo["els"])
            if missing:
                raise DemoError(f"the report has no {sorted(missing)} to scroll to")
            stops = [min(max(0, geo["els"][i][0] - 0.2 * SIZE[1]), geo["max"]) for i in ("demo-pricing", "demo-terms")]
            for k, y in enumerate(scroll_positions(stops, fps)):
                y = round(y)
                page.evaluate("y => window.scrollTo(0, y)", y)
                if seen is not None:
                    for name, (top, bottom) in geo["els"].items():
                        if top >= y and bottom <= y + SIZE[1]:
                            seen.setdefault(name, []).append(first_frame + k)
                yield Image.open(BytesIO(page.screenshot(type="png"))).convert("RGB")
        finally:
            browser.close()


# ------------------------------------------------------------------ closing card

def closing_card(scan_date):
    img = Image.new("RGB", SIZE, TERM_BG)
    draw = ImageDraw.Draw(img)
    cx = SIZE[0] / 2
    small, body, big = load_font(SANS_FONTS, 26), load_font(SANS_FONTS, 30), load_font(SANS_BOLD_FONTS, 46)
    draw.text((cx, 230), f"github.com/{REPO_OWNER}", font=small, fill=PALETTE["brightblack"], anchor="mm")
    draw.text((cx, 290), REPO_NAME, font=big, fill=(250, 250, 250), anchor="mm")
    draw.text((cx, 400), f"one scan of a public storefront, {scan_date},", font=body, fill=TERM_FG, anchor="mm")
    draw.text((cx, 446), "nothing fabricated: blocked sites are reported as blocked", font=body,
              fill=TERM_FG, anchor="mm")
    draw.text((cx, 560), "rendered by scripts/make_demo_video.py", font=small, fill=PALETTE["brightblack"], anchor="mm")
    return img


# ------------------------------------------------------------------ encoding

def ffmpeg_exe():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def encode_mp4(frames, path, fps=FPS):
    import imageio_ffmpeg
    writer = imageio_ffmpeg.write_frames(str(path), SIZE, fps=fps, codec="libx264", quality=None,
                                         ffmpeg_log_level="error",
                                         output_params=["-crf", "20", "-preset", "medium", "-movflags", "+faststart"])
    writer.send(None)
    n = 0
    try:
        for frame in frames:
            writer.send(frame.tobytes())
            n += 1
    finally:
        writer.close()
    return n


def concat_mp4(parts, out):
    listing = out.with_suffix(".txt")
    listing.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in parts), encoding="utf-8")
    subprocess.run([ffmpeg_exe(), "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
                    "-c", "copy", "-movflags", "+faststart", str(out)], check=True)
    listing.unlink()


def encode_gif(mp4, gif, fps, width, palette):
    vf = f"fps={fps},scale={width}:-2:flags=lanczos"
    subprocess.run([ffmpeg_exe(), "-y", "-v", "error", "-i", str(mp4), "-vf", f"{vf},palettegen=stats_mode=diff",
                    str(palette)], check=True)
    subprocess.run([ffmpeg_exe(), "-y", "-v", "error", "-i", str(mp4), "-i", str(palette), "-lavfi",
                    f"{vf} [x]; [x][1:v] paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle", str(gif)],
                   check=True)
    return gif.stat().st_size


def choose_gif_settings(encode, target=GIF_TARGET, limit=GIF_LIMIT, ladder=GIF_LADDER):
    """Encode down the ladder until the GIF is at most `target` bytes; the last step must be at most
    `limit`. The file left on disk is the one encoded last, which is the one returned."""
    for fps, width in ladder:
        size = encode(fps, width)
        if size <= target:
            return {"fps": fps, "width": width, "size": size, "over_target": False}
    if size > limit:
        raise DemoError(f"the GIF is {size / MB:.1f} MB at {fps} fps and {width} px, "
                        f"over the {limit / MB:.1f} MB limit")
    return {"fps": fps, "width": width, "size": size, "over_target": True}


# ------------------------------------------------------------------ main

def _ranges(frames):
    out = []
    for f in sorted(set(frames)):
        if out and f == out[-1][1] + 1:
            out[-1][1] = f
        else:
            out.append([f, f])
    return [f"{a}-{b}" for a, b in out]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--site", default=DEFAULT_SITE, help=f"the store to scan (default {DEFAULT_SITE})")
    parser.add_argument("--work", default=str(REPO / "output" / "demo-video"), help="working directory")
    parser.add_argument("--docs", default=str(REPO / "docs"), help="where demo.mp4 and demo.gif go")
    parser.add_argument("--reuse-run", action="store_true", help="render from <work>/run without a new scan")
    args = parser.parse_args(argv)

    work, docs = Path(args.work).resolve(), Path(args.docs).resolve()
    run_dir, acts = work / "run", work / "acts"
    acts.mkdir(parents=True, exist_ok=True)
    if args.reuse_run:
        cast = run_dir / "session.cast"
        if not cast.is_file():
            raise DemoError(f"no recording at {cast}; run without --reuse-run first")
    else:
        print(f"Scanning {args.site} once (robots.txt respected, default delays) ...", flush=True)
        cast = capture_run(run_dir, args.site)
    header, raw = read_cast(cast)
    check_no_private_paths("".join(data for _, code, data in raw if code == "o"))
    scan_date = datetime.fromtimestamp(header["timestamp"]).strftime("%Y-%m-%d")

    seen = {}
    speed, events, window = plan_terminal(raw)
    n1 = encode_mp4(render_terminal_frames(events, header["width"], header["height"], FPS, HOLD_END, window,
                                           f"{speed}x", watch=("Sites analyzed: 1", "Generated business report",
                                                               "Shopify sites: 1", "Complete!"), seen=seen),
                    acts / "act1.mp4")
    report_md = run_dir / "output" / "business_report.md"
    html_path = work / "business_report.html"
    html_path.write_text(markdown_to_html(report_md.read_text(encoding="utf-8")), encoding="utf-8")
    n2 = encode_mp4(report_frames(html_path, FPS, first_frame=n1, seen=seen), acts / "act2.mp4")
    card = closing_card(scan_date)
    n3 = encode_mp4((card for _ in range(round(CARD_SECONDS * FPS))), acts / "act3.mp4")

    docs.mkdir(parents=True, exist_ok=True)
    mp4, gif = docs / "demo.mp4", docs / "demo.gif"
    concat_mp4([acts / "act1.mp4", acts / "act2.mp4", acts / "act3.mp4"], mp4)
    chosen = choose_gif_settings(lambda fps, width: encode_gif(mp4, gif, fps, width, work / "palette.png"))

    manifest = {
        "site": args.site, "scan_date": scan_date, "speed": f"{speed}x", "fast_window_s": window,
        "acts_s": {"terminal": n1 / FPS, "report": n2 / FPS, "card": n3 / FPS},
        "frames": {"terminal": [0, n1 - 1], "report": [n1, n1 + n2 - 1], "card": [n1 + n2, n1 + n2 + n3 - 1]},
        "mp4_bytes": mp4.stat().st_size, "gif": chosen,
        "visible_frames": {k: _ranges(v) for k, v in seen.items()},
    }
    (work / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(json.dumps(manifest, indent=1))
    if chosen["over_target"]:
        print(f"warning: demo.gif is {chosen['size'] / MB:.1f} MB, over the {GIF_TARGET / MB:.0f} MB target")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except DemoError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
