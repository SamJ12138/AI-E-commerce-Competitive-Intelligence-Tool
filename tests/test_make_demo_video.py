"""scripts/make_demo_video.py: the steps that need no network and no browser. The real run (one
scan of a public store, then Playwright and ffmpeg) is not part of the fast suite."""

import math
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import make_demo_video as mdv  # noqa: E402

CAST = REPO / "tests" / "fixtures" / "demo" / "ten_lines.cast"
ALLBIRDS = REPO / "docs" / "sample" / "real" / "allbirds" / "business_report.md"
MB = 1024 * 1024


# ---------------------------------------------------------------- cast -> frames

def test_read_cast():
    header, events = mdv.read_cast(CAST)
    assert (header["width"], header["height"]) == (60, 14)
    assert sum(1 for e in events if e[1] == "o") == 12
    assert [e[2] for e in events if e[1] == "m"] == ["fast-start", "fast-end"]


def test_retime_speeds_up_the_marked_part_and_cuts_long_pauses():
    _, events = mdv.read_cast(CAST)
    out, window = mdv.retime(events, speed=8, max_gap=0.4)
    times = [round(t, 4) for t, code, _ in out if code == "o"]
    # 0.5 s before the fast part -> 0.4; 0.8 s gaps inside it / 8 -> 0.1; 2 s pause after it -> 0.4
    assert times == [0.0, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.9125, 1.3125, 1.4125, 1.5125, 1.6125]
    assert window == pytest.approx((0.4, 0.9125))
    assert all(b - a <= 0.4 + 1e-9 for a, b in zip(times, times[1:]))


def test_screen_text_runs_the_escape_codes():
    _, events = mdv.read_cast(CAST)
    lines = mdv.screen_text(events, 60, 14)
    assert lines[0].startswith("$ python main.py --sites sites.txt --lang en")
    assert lines[5].rstrip() == "line 05 progress 100%"   # \r + erase line overwrote "progress 50%"
    for n in range(1, 11):
        assert any(line.startswith(f"line {n:02d}") for line in lines), n
    assert not any("\x1b" in line or "[32m" in line for line in lines)


def test_cast_to_frames_on_the_ten_line_fixture():
    frames = list(mdv.cast_to_frames(CAST, fps=10, hold=0.5, speed=8, max_gap=0.4))
    assert len(frames) == math.ceil((1.6125 + 0.5) * 10) == 22
    assert all(f.size == (1280, 720) and f.mode == "RGB" for f in frames)
    # nothing typed yet at t=0 beyond the first line; the last frame has more ink than the first
    assert _ink(frames[-1]) > _ink(frames[0]) > 0
    # the speed label shows exactly on the frames inside the sped-up part (0.4 s to 0.9125 s)
    labelled = [i for i, f in enumerate(frames) if _ink(f.crop(mdv.LABEL_BOX)) > 0]
    assert labelled == [4, 5, 6, 7, 8, 9]


def _ink(img):
    """Number of pixels that differ from the background colour."""
    from PIL import Image, ImageChops
    diff = ImageChops.difference(img, Image.new("RGB", img.size, mdv.TERM_BG)).convert("L")
    return img.size[0] * img.size[1] - diff.histogram()[0]


def test_private_paths_are_refused():
    assert mdv.private_path_hits("Run log: logs/run_1.jsonl\r\nReports: output/report.md") == []
    assert mdv.private_path_hits(f"Run log: {Path.home() / 'x' / 'run.jsonl'}")
    with pytest.raises(mdv.DemoError):
        mdv.check_no_private_paths(f"saved to {Path.home()}")


# ---------------------------------------------------------------- markdown -> HTML

def test_business_report_to_html_keeps_the_headings():
    html = mdv.markdown_to_html(ALLBIRDS.read_text(encoding="utf-8"))
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    heads = [(h.name, h.get_text(" ", strip=True)) for h in soup.find_all(["h1", "h2", "h3"])]
    assert heads == [
        ("h1", "Competitive Intelligence Report"),
        ("h2", "Executive Summary"),
        ("h3", "Key Findings"),
        ("h2", "Site Profiles"),
        ("h3", "www.allbirds.com"),
        ("h2", "Recommendations"),
        ("h2", "Appendix"),
        ("h3", "Methodology"),
        ("h3", "Data Quality Notes"),
    ]
    assert soup.find("table") is not None            # the evidence table is a real table
    assert soup.find("style") is not None            # the stylesheet is inline
    for tag in ("link", "script", "img", "iframe"):  # no external assets
        assert soup.find(tag) is None, tag
    assert "@import" not in html and "url(" not in html


def test_business_report_html_marks_the_scroll_stops():
    html = mdv.markdown_to_html(ALLBIRDS.read_text(encoding="utf-8"))
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    sites, pricing, terms = (soup.find(id=i) for i in ("demo-sites", "demo-pricing", "demo-terms"))
    assert "Sites Analyzed" in sites.get_text() and "1" in sites.get_text()
    assert "$14" in pricing.get_text() and "$145" in pricing.get_text()
    assert "Shipping" in terms.get_text() and "Returns" in terms.get_text()
    order = [el for el in soup.find_all(True) if el.get("id", "").startswith("demo-")]
    assert [el["id"] for el in order] == ["demo-sites", "demo-pricing", "demo-terms"]


def test_html_prefers_a_pricing_table_when_the_report_has_one():
    md = ("# R\n\n**Sites Analyzed:** 2\n\n## Comparison\n\n"
          "| Site | Price Range | Free Shipping | Returns |\n|---|---|---|---|\n"
          "| a.com | $10-$20 | $50+ | 30d |\n| b.com | $5-$9 | ❌ | 14d |\n")
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(mdv.markdown_to_html(md), "lxml")
    assert soup.find(id="demo-pricing").name == "table"
    assert soup.find(id="demo-terms") is not None


# ---------------------------------------------------------------- GIF size guard

def _encoder(sizes):
    calls = []

    def encode(fps, width):
        calls.append((fps, width))
        return sizes[(fps, width)]
    return encode, calls


def test_gif_under_target_keeps_10_fps_960_px():
    encode, calls = _encoder({(10, 960): 4 * MB})
    assert mdv.choose_gif_settings(encode) == {"fps": 10, "width": 960, "size": 4 * MB, "over_target": False}
    assert calls == [(10, 960)]


def test_gif_over_target_drops_to_8_fps_then_800_px():
    encode, calls = _encoder({(10, 960): 6 * MB, (8, 960): 5.5 * MB, (8, 800): 4.9 * MB})
    got = mdv.choose_gif_settings(encode)
    assert (got["fps"], got["width"], got["over_target"]) == (8, 800, False)
    assert calls == [(10, 960), (8, 960), (8, 800)]

    encode, calls = _encoder({(10, 960): 6 * MB, (8, 960): 4.5 * MB})
    assert mdv.choose_gif_settings(encode)["fps"] == 8 and calls == [(10, 960), (8, 960)]


def test_gif_over_target_but_under_limit_is_kept_and_flagged():
    encode, _ = _encoder({(10, 960): 9 * MB, (8, 960): 8.5 * MB, (8, 800): 6 * MB})
    got = mdv.choose_gif_settings(encode)
    assert (got["width"], got["over_target"]) == (800, True)


def test_gif_over_the_limit_fails():
    encode, _ = _encoder({(10, 960): 9 * MB, (8, 960): 8.5 * MB, (8, 800): 8 * MB + 1})
    with pytest.raises(mdv.DemoError, match="8.0 MB"):
        mdv.choose_gif_settings(encode)
