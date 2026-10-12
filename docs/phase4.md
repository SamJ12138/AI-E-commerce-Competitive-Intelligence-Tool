# Phase 4 changes

Release preparation. One section per batch, in commit order. Each code change: RED test first, then
the fix, full suite through the pre-commit hook.

## Batch A - honest-User-Agent retry, Crawl-delay, a store instead of a clinic

### Honest-User-Agent retry

- Default chain: the browser-like request goes first, as before. On a 403 or 429 the same URL is
  asked once more by the `honest-ua` branch: User-Agent
  `ECI-Tool/1.0 (E-commerce Competitive Intelligence Tool; +https://github.com/SamJ12138/AI-E-commerce-Competitive-Intelligence-Tool)`
  with plain Accept / Accept-Language / Accept-Encoding and none of the browser headers
  (`sec-ch-ua`, `Sec-Fetch-*`, `Upgrade-Insecure-Requests`, `DNT`). It waits the per-host delay
  first. A 403 after that goes on to cloudscraper as before; a 429 does not (cloudscraper only ever
  followed a 403). The `--render-js` chain (browser, then cloudscraper) is unchanged.
- robots.txt gets the same retry: a 403/429 to the browser-like User-Agent is asked once more with
  the honest one before it is taken as "no robots.txt" (RFC 9309 4xx).
- 429 now reaches the chain: urllib3 retried 429 itself and, after the last retry, raised a
  RetryError, so `fetch()` saw status 0 ("no HTTP answer") and a rate-limited site was reported as
  unreachable. `raise_on_status=False` returns the final 429 response.
- Every chain entry in the obs `fetch` event carries `identity` (browser-like headers / honest
  User-Agent / cloudscraper (Chrome) / headless browser); the event's own `identity` is the one
  that got the page. Reports name the branch ("requests with the tool's own User-Agent").
- Fixture: `StoreServer(..., refuse_browser_ua=True)` answers 403 to anything with a `Mozilla/`
  User-Agent or `Sec-Fetch-*` headers, robots.txt included (barefootbuttons' behaviour), and serves
  the store otherwise. shopify_basic behind it ends `status=ok` with every page asked twice
  (403, then 200) and Shopify's robots rules applied.
- RED (sources unchanged, new tests): `tests/test_honest_ua.py` 10 of 13 failed (status
  `blocked`; robots.txt never retried; chains `requests -> cloudscraper`; a 429 came back as status
  0); the 200 / 404 / `--render-js` chain cases passed. `test_blocked.py` (2) and
  `test_fetch_provenance.py` now spell out the `honest-ua` step.

### robots.txt Crawl-delay

- `analyze_site` sets the per-host delay to `max(rate_limit_delay, Crawl-delay)` before the first
  request to the site. `RateLimiter` keeps per-host delays (`delay_for(host)`). An obs `robots`
  event `kind=crawl_delay` records Crawl-delay, the config delay and the delay used; when
  Crawl-delay raises it, a log line says so ("robots.txt Crawl-delay 60 s raises the delay between
  requests to ... from 1.5 s to 60 s"). `--ignore-robots` ignores Crawl-delay too.
- Crawl-delay is read from the `User-agent: *` group (the group `is_allowed()` reads) by the tool
  itself: robotexclusionrulesparser drops a group that has no Allow/Disallow line, so
  `User-agent: *` + `Crawl-delay: 5` alone came back as None.
- RED: `tests/test_crawl_delay.py` 6 of 6 failed (no per-host delay). Absent and smaller keep the
  config delay; larger (0.6 s over 0.1 s) spaces the fixture store's page requests at least 0.55 s
  apart; another agent's Crawl-delay does not apply.

### Real stores

- **barefootbuttons, rerun once** (cloudscraper off, default settings): `blocked` (requests 403)
  -> `ok`. robots.txt and all 9 pages answered 403 to the browser-like request; the honest retry got
  200 on 7 pages and 404 on one guessed page; `/privacy-policy` ended "Exceeded 30 redirects" on the
  browser-like request (no retry: not a 403/429). Score 3/0/1/6 -> 8/0/2/0 (two new single-store
  misses, docs/observations.md section 9).
- **pfrankmd.com replaced by beardbrand.com** (Shopify, men's grooming) in sites.txt, main.py's
  examples and the corpus. Ground truth read first (10 pages, same method as the other stores,
  `docs/real-corpus/beardbrand.json`), then one tool run: 5/1/2/2.
- `docs/real-corpus/scores.md` is now the current table (8 stores; six of them are the Phase 3
  Batch 4 runs); the Phase 3 baseline moved to `scores-baseline.md`. Totals over 80 store-fields:
  62 match / 5 partial / 9 mismatch / 4 missing.

### A race in the fixture server

The first commit attempt was refused by the hook: `test_page_loop.py::test_policies_are_read_after_max_products_is_reached`
failed once (the request log lacked `/policies/refund-policy`, the last page fetched) and passed on
rerun; 1 failure in 8 full-suite runs. `StoreServer` recorded a request after writing its
response, so a test reading `request_log()` as soon as the client had the body could miss the last
request. It now records first. RED: `test_a_request_is_recorded_before_its_response_is_sent`
(the recording delayed by 0.3 s) saw an empty log.

Tests 238 -> 258. Fixture scores 17/0/0 on all four runs; the blocked runs now make 5 and 6
requests (robots.txt and the homepage are each asked once more with the honest User-Agent).

## Batch B - license, hygiene test, fetching doc, cleanup

- **Personal-data sweep** (school name and login, local account name, mail provider, Windows and
  Linux home paths) over the
  tracked files and `git log -p --all`. Working tree: 36 hits, all absolute local paths inside the
  four committed run logs in `docs/baseline/logs/` (`sites_file`, `config`, `db_path`). History: the
  same 36 in the commit that added those logs, plus the author/committer line of every commit (the
  school address). No hit in any commit message or other file. The logs now say `<out>` for the
  scorer's output directory; `score_fixtures.py --baseline-dir` writes them that way
  (`scrub_paths()`).
- `tests/test_repo_hygiene.py`: no personal-data pattern in any tracked file or path (patterns are
  assembled from pieces so the test does not match itself); LICENSE (MIT, 2026 Tianyi Jia) and
  NOTICE.md exist; config.yaml is ignored; config.example.yaml lists exactly the keys main.py
  reads, each with a comment, with the defaults as values; config-file values are used unless the
  command line sets them.
- **Config bug found by that test:** `--timeout`, `--max-products` and `--max-pages` had click
  defaults (30 / 50 / 20), and `cli or config` always took the CLI value, so those three keys in a
  config file were never used. The options now default to None and `main.CONFIG_KEYS` holds the
  defaults (command line > file > default). Keys main.py never read (`sites_file`, `output_dir`,
  `user_agent`, `language`, `page_priority`, `category_keywords`) are gone from the example.
- NOTICE.md: nothing third-party is bundled; fixtures imitate theme and challenge-page markup.
- `docs/history/` deleted; `docs/fetching.md` describes robots.txt handling, the default chain
  (browser-like headers -> own User-Agent on 403/429 -> cloudscraper on 403), the `--render-js`
  chain (browser -> cloudscraper), and when a site ends ok / blocked / unreachable / skipped.
  Module docstrings in `http_client.py` and the requirements comments now describe the chain in the
  same terms (the code path is unchanged, A3).
- Removed: `CLICK_TO_RUN.bat`, `CLICK_TO_RUN.command`, `START.ps1`, `START.sh`, `run.ps1`,
  `setup.ps1`, `POWERSHELL_GUIDE.md` (the README quickstart replaces them), `QUICKSTART.md` (same),
  `PRICING_PATTERNS.md` (v15 notes: "expected results after fixes" never measured; the patterns are
  documented in `modules/price_extractor.py`), `architecture-clean.svg` (shows the threat score and
  ML pricing removed in Phase 2 and an evidence level never produced).

RED: `tests/test_repo_hygiene.py` 6 of 7 failed (36 personal-data hits; no LICENSE; no
`main.CONFIG_KEYS`; the config file's `timeout: 7` / `max_pages: 3` / `max_products: 4` resolved to
30 / 20 / 50; no `scrub_paths`); `config.yaml` was already ignored. Tests 258 -> 265. Fixture scores
17/0/0 on all four runs.

## Batch C - README

- `README.md` rewritten for someone who has never seen the project: what it does and for whom;
  a quickstart (clone, venv, `pip install -r requirements.txt`, `scripts/demo.py`) in PowerShell
  and bash that calls the venv's Python directly (no activation, so no execution-policy prompt);
  real stores and every option; fetching in three sentences plus "Responsible use"; accuracy
  (fixtures 68/68, the real-store table per field, the Brotli finding); the CSV columns and the two
  Markdown reports; what "AI" means (only `--ai`) with the pressure-score weights; development;
  limitations; license.
- `scripts/demo.py` serves the three fixture stores on 127.0.0.1 (ports 8701-8703 when free),
  runs `main.py` on them with no delay between requests and a fresh scan history, and prints
  where the reports are. About 2 seconds.
- `docs/sample/` (English) and `docs/sample/zh/` (Chinese): the three reports from
  `scripts/demo.py`, as generated.
- **Bug found by the first demo run:** on a console whose code page cannot encode the emoji
  `main.py` prints (here GBK with output piped; also cp1252 or ASCII), the run ended with
  `UnicodeEncodeError` before the first fetch. Every test harness set `PYTHONIOENCODING=utf-8`, so
  no test saw it. `main()` now sets `errors="replace"` on stdout and stderr.
- `tests/test_demo_and_readme.py`: the demo writes the three reports (two `ok`, one `blocked`) and
  prints their paths; the committed sample exists; every relative link in the README resolves;
  every `--option` the README names exists; the quickstart runs the demo; `main.py` finishes with
  `PYTHONIOENCODING` = ascii / gbk / cp1252.

RED: 4 of 6 README/demo tests failed (no demo.py, no sample, quickstart missing); the console test
failed for all three encodings (`UnicodeEncodeError: ... '\U0001f50d'`). Tests 265 -> 274.

## Batch D - stopped: the repository has a fork

`gh repo view`: forkCount 1, stargazerCount 3. The fork is `shhnn/-123` (public, created
2026-03-28, no pushes of its own since it was made). The remote also has a tag `updates`
(9182567, in the old history) besides `main`. Per the brief, nothing was pushed, no backup bundle
or new history was built; waiting for the owner.

## Batch E rehearsal (local, before any push)

A fresh clone of the local branch into a new temp folder, following the README's PowerShell
quickstart literally: clone 1 s, venv 4 s, `pip install -r requirements.txt` 12 s (packages
cached on this machine), demo 3 s, total 19 s; the three reports in `output/demo/`. The first
attempt, from a 150-character folder, failed in pip: lxml installs a file whose full path passed
Windows' 260-character limit. The README now says what that error looks like and to clone into a
shorter folder. Python 3.10.6 (the oldest version the README names): install clean, 274 passed.
