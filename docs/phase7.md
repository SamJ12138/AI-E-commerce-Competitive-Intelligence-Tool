# Phase 7: README demo video

A demo video for the top of the README, rendered entirely by `scripts/make_demo_video.py` so the
same clip can be made again. One real store (allbirds.com) was scanned once for it.

## 1. The script (9142c5e)

- Three acts, each encoded to its own h264 file (1280x720, 30 fps) and concatenated with the ffmpeg
  binary that ships in the imageio-ffmpeg wheel; `docs/demo.gif` is made from the MP4 with a
  two-pass palette (960 px, 10 fps; then 8 fps, then 800 px while over 5 MB; over 8 MB fails).
- Act 1, terminal. asciinema and agg are not installed here and have no native Windows build, so
  the run is recorded without a pty: `main.py` writes into a pipe, rich is told it is a 100x27
  terminal (`TTY_COMPATIBLE`, `TTY_INTERACTIVE`, `COLUMNS`, `LINES`; rich's legacy-Windows renderer is
  switched off in the launching process so it writes VT escape codes), and each chunk is stored
  with its time in an asciinema v2 file, `output/demo-video/run/session.cast`. The cast is replayed
  through pyte (a VT100 emulator) and every frame drawn with Pillow. The typed `cat sites.txt` and
  command line are added by the script; the command shown is the one run (`--sites sites.txt
  --lang en`, working directory `output/demo-video/run`), so every path on screen is relative, and
  the script refuses a recording that contains a home-directory path. As in
  `scripts/real_corpus.py`, cloudscraper is switched off for the real run.
- Speed: the part from main.py's first line to "Generating reports" plays at 8x with an "8x" label;
  if the act would reach 10 s the factor doubles (the label shows the factor used). After that,
  pauses over 0.4 s become 0.4 s; the last screen is held 1.5 s.
- Act 2, report. `business_report.md` to HTML with markdown-it-py (already installed with rich) and
  an inline stylesheet, opened in headless Chromium with every non-file request aborted, scrolled
  with one screenshot per frame: 2.5 s at the top, then 1.25 s to each stop and 1.5 s on it.
- What the brief asked for and the code does not have:
  - A one-store business report has no pricing table and no shipping/returns table: the
    comparison matrix is written only for two or more stores. The stops are the comparison table
    when there is one, otherwise the "Pricing" finding and the store's "Key Metrics" list (price
    range, shipping, returns).
  - There is no platform-detection line on the console, only the transient progress text
    "Detecting platform..." (a frame or two at 8x) and "Shopify sites: 1" in the summary, which is
    on the held last screen.
  - The report line is "Sites Analyzed: 1"; "Sites analyzed: 1" is the console summary. Both are
    in the video.
- `requirements-dev.txt` (pytest, pyte, pillow, imageio-ffmpeg) is what CI installs now; the CI
  guard test checks that it pulls in requirements.txt.
- RED: the new test module failed at import (no script). GREEN: 12 new tests (cast reading,
  retiming, screen replay, cast to frames on a 10-line fixture cast including which frames carry the
  label, private paths, markdown to HTML headings on the allbirds sample, scroll stops, GIF size
  guard); two existing guard tests needed the change described above (CI installs the dev file;
  the README may not name script flags as if they were main.py flags). Full suite 406 passed.
- Before the real run the whole pipeline ran once against the local Shopify fixture store
  (no real site): 16.4 s, GIF 2.3 MB.

## 2. The video

- One run, 2026-10-12, `https://www.allbirds.com`, default settings: about 26 s of fetching, 19
  pages discovered (the shipping-policy page skipped by robots.txt), 50 priced products from $14 to
  $145, median $105, free shipping over $100, 30-day returns. Same figures as the Phase 5 scan in
  docs/sample/real/allbirds; "Marketing" now lists only email capture, because since Phase 6 a
  popup drawn only by a script is unknown.
- Found in this report, not fixed (open for the owner): recommendation 4 reads "this site collects
  emails without a popup", but has_popup is unknown (None), not false. `business_report.py` picks
  the wording with `if intel.has_popup`, so None reads as "without". It is on screen at the end of
  act 2. Fixing it changes the report, so the video would need a new scan (or a decision to
  rebuild the report from the stored snapshot) to show the corrected line.
- Acts: terminal 8.73 s (frames 0-261, fetch at 8x), report 8.03 s (262-502), card 2.0 s
  (503-562); `docs/demo.mp4` 18.77 s, 0.4 MB.
- In the MP4: the progress line at 100%, "Generated business report" and "Sites analyzed: 1" are
  on screen in frames 217-261; in the report, "Sites Analyzed: 1" in 262-354, the pricing finding
  in 262-433 and the Key Metrics list (shipping and returns) in 367-502. The GIF frame is the MP4
  frame divided by 3.
- `docs/demo.gif`: 960x540, 10 fps, 188 frames, 2.33 MB (under the 5 MB target, first step of the
  ladder).
- To render again without a new scan: `python scripts/make_demo_video.py --reuse-run` (the
  recording and the run's reports stay in `output/demo-video/run`, which is not committed).
