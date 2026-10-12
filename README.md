# E-commerce Competitive Intelligence Tool

Point it at competitor online stores and it writes a structured comparison of what each store
shows a shopper: prices and discounts, shipping and return terms, promotions (announcement bar,
email signup, popups, loyalty and referral programs), trust signals (review platform, payment
methods, tracking pixels), plus a business summary across the stores, in English or Chinese. It is
for small cross-border and direct-to-consumer sellers who want to see how their own store compares
with a handful of competitors on Shopify, WooCommerce and similar platforms, without paying for a
market-research service.

## Quickstart (no network needed after install)

Requires Python 3.10 or newer and git. This runs the tool on three small stores bundled with the
repository (served on your own machine), so nothing is sent to any real website.

PowerShell:

```powershell
git clone https://github.com/SamJ12138/AI-E-commerce-Competitive-Intelligence-Tool.git
cd AI-E-commerce-Competitive-Intelligence-Tool
python -m venv venv
venv\Scripts\python -m pip install -r requirements.txt
venv\Scripts\python scripts\demo.py
```

bash (Linux, macOS):

```bash
git clone https://github.com/SamJ12138/AI-E-commerce-Competitive-Intelligence-Tool.git
cd AI-E-commerce-Competitive-Intelligence-Tool
python3 -m venv venv
venv/bin/python -m pip install -r requirements.txt
venv/bin/python scripts/demo.py
```

The demo serves a Shopify-style store, a WooCommerce-style store and a store that answers every
request with a 403 challenge page, runs the tool on all three, and writes three reports to
`output/demo/`:

- `output/demo/report.md` - one section per store, and a comparison table
- `output/demo/report.csv` - one row per store, one column per field
- `output/demo/business_report.md` - a summary across the stores

Add `--lang zh` to the demo command for Chinese reports. The commands call the virtual
environment's Python directly, so there is no activation step (and no PowerShell execution-policy
prompt). On Windows, if pip stops with "No such file or directory" and a hint about long paths,
the folder is too deep for the 260-character path limit: clone into a shorter folder (for example
`C:\src`) and start again.

## Running on real stores

Put the stores in `sites.txt`, one URL per line (lines starting with `#` are comments), then:

```powershell
venv\Scripts\python main.py --sites sites.txt --lang en
```

(`venv/bin/python` in bash.) Reports go to `output/` (`--outdir` to change it). The run log goes to
`logs/`.

| option | what it does |
|---|---|
| `--lang en` / `--lang zh` | Report language. The default is `zh` (Chinese). |
| `--render-js` | Load pages in a headless browser so prices and menus drawn by JavaScript are seen. Run `venv\Scripts\python -m playwright install chromium` once first. Slower. |
| `--ai` | Add text written by a local language model (see below). |
| `--ai-model` | The Ollama model for `--ai` (default `qwen2.5:7b`). |
| `--monitor` | Compare each store with its previous scan and report what changed. |
| `--max-pages`, `--max-products` | Pages read and products collected per store (defaults 20 and 50). |
| `--max-per-collection` | Products taken from one collection page (default 10), so one big collection does not fill the sample. When every page is read and the sample is still under `--max-products`, it is topped up from the collection pages already read. |
| `--timeout` | Seconds to wait for one response (default 30). |
| `--config` | A settings file; copy `config.example.yaml` to `config.yaml`, which documents every key. |
| `--ignore-robots` | Ignore robots.txt rules and Crawl-delay. Only for sites you own or have permission to crawl. |
| `--verbose` | Debug logging. |

**`--ai` (optional).** Install [Ollama](https://ollama.com), run `ollama pull qwen2.5:7b`, and
add `--ai`. For every store that was read, the local model writes key insights, recommendations
and a brand-positioning paragraph; they appear in `report.md` under headings marked "(AI)". The
model's text is in Chinese whatever `--lang` says. Nothing is sent to a cloud service. Without
`--ai`, or when Ollama is not running (a warning says so), all text is rule-based and the
business report says the LLM step did not run.

The `--ai` step is implemented but has not been verified with a real model: Ollama was not
installed on the machine this was developed on. It is tested end to end against a fake Ollama
client (`tests/test_ai_fake_ollama.py`: what the model is asked, and where its answer appears in
the reports), not for the quality of what a real model writes.

**Monitor mode and change detection.** Every scan is stored in `data/intel_cache.db`. With
`--monitor`, each store is compared with the newest earlier scan of the same store and `report.md`
lists what changed: lowest and highest price, announcement bar text, featured products added or
removed, categories, free-shipping threshold and return window. A store that was blocked on either
scan is not compared. Run the same command on a schedule (Task Scheduler, cron) to track
competitors over time.

## How fetching works

Each page is requested with browser-like headers (a desktop Chrome User-Agent); if the server
answers 403 or 429, the same URL is asked once more with a User-Agent that names this tool and
links to this repository, and after a further 403 the tool falls back to cloudscraper, which can
answer Cloudflare's JavaScript challenge; with `--render-js` pages are loaded in a headless browser
instead, with cloudscraper as its fallback. robots.txt rules and Crawl-delay are respected unless
`--ignore-robots` is passed, and by default the tool waits 1.5 seconds between requests to the same
host. A
store that refuses every attempt is reported as blocked, with the steps tried, and none of its
fields are guessed. Every step and when a store ends as blocked or unreachable:
[docs/fetching.md](docs/fetching.md).

**Responsible use.** Check each site's terms of service before you scan it; some forbid automated
access whatever their robots.txt says. Keep the delays: do not lower `rate_limit_delay` or pass
`--ignore-robots` for sites that are not yours. Scan competitors for your own analysis; do not use
the tool to collect data for resale. You are responsible for how you use it.

## Accuracy

**Fixture stores.** Three hand-written stores in `tests/fixtures/stores/`, each with the true value
of every field in its `fixtures.json`. Four runs (the Shopify-style store, the WooCommerce-style
store, the blocked store, and the blocked store with `--render-js`), 17 fields each: 68 of 68
match, checked on every commit. The fixtures were written alongside the extractors, so this shows
the code does what the tests describe, not how it does on real stores.

**Real stores.** Eight public stores (five Shopify, two WooCommerce, one Magento store behind a
Cloudflare challenge), with the true values read by hand from their pages and the source URL of
every fact in [docs/real-corpus/](docs/real-corpus/README.md). One run per store, default settings
(brooklinen, whose catalogue is drawn by JavaScript, with `--render-js`), cloudscraper switched off.
Per field, out of 8 stores
([docs/real-corpus/scores.md](docs/real-corpus/scores.md)):

| field | match | partial | mismatch | missing |
|---|---|---|---|---|
| status (ok / blocked) | 8 | 0 | 0 | 0 |
| platform | 8 | 0 | 0 | 0 |
| products (price and compare-at price of 4 known products) | 7 | 0 | 1 | 0 |
| free-shipping threshold | 8 | 0 | 0 | 0 |
| return window (days) | 8 | 0 | 0 | 0 |
| free returns | 8 | 0 | 0 | 0 |
| payment methods | 7 | 1 | 0 | 0 |
| review platform | 8 | 0 | 0 | 0 |
| loyalty program | 7 | 0 | 1 | 0 |
| email capture | 8 | 0 | 0 | 0 |
| marketing popup (unknown on 5 stores: drawn by a script) | 7 | 0 | 0 | 1 |
| **total (88)** | **84** | **1** | **2** | **1** |

"Missing" means the store states a value and the tool reported none; "mismatch" means the tool
reported a wrong value, including a definite answer where the store states nothing. The blocked
Magento store counts as a match on every field when the tool reports it as blocked with every field
unknown. The remaining misses are listed one by one in
[docs/observations.md](docs/observations.md) (sections 8 to 13); two of them are disagreements between
the ground truth and the store's pages, left for a decision ([docs/phase5.md](docs/phase5.md)). The
popup miss (brooklinen) was fixed after its run ([docs/phase6.md](docs/phase6.md)).

**Why there is a real-store corpus.** When it was first run, six of the eight real stores came
back empty: they answered with Brotli-compressed pages, the tool asked for Brotli without a decoder
installed, and parsed the compressed bytes as HTML. Every fixture test passed at the time, because
the fixture server does not compress. The first real-store score was 36 match, 8 mismatch, 36
missing out of 80 ([docs/real-corpus/scores-baseline.md](docs/real-corpus/scores-baseline.md)).

## Output

`report.csv` has one row per store:

| column | content |
|---|---|
| `domain`, `url` | the store |
| `status`, `fetch_attempts` | `ok`, `blocked` or `unreachable`; for a store that was not read, the steps tried and their status codes |
| `platform` | Shopify, WooCommerce, Magento, BigCommerce, PrestaShop, Squarespace, Wix or Custom/Unknown |
| `brand_positioning` | the store's own description of itself, quoted (meta description, title tagline or hero headline) |
| `categories` | categories from the navigation |
| `price_min`, `price_max`, `price_median`, `currency` | over the products read; empty when no product read had a price (other amounts on the page are never used) |
| `has_discounts` | a product shows a compare-at (struck-through) price |
| `announcement_bar` | the text of the bar at the top of the page |
| `has_popup` | a marketing popup (a sign-up or offer overlay the store opens by itself, or an exit-intent overlay) is in the page; empty when none is but a script that draws popups in the browser is loaded (Klaviyo, Attentive, Postscript, ...) |
| `has_email_capture`, `has_loyalty`, `has_referral` | marketing features found |
| `free_shipping_threshold`, `return_days`, `free_returns` | shipping and return terms |
| `review_platform`, `review_count` | the review app (Yotpo, Judge.me, ...) and the number of reviews shown |
| `payment_methods` | cards, wallets and buy-now-pay-later services named or declared on the pages |
| `pixels_detected` | analytics and ad pixels (Google Analytics, Meta Pixel, ...) |
| `scan_timestamp` | when the store was scanned |

Empty cells mean unknown. For a blocked or unreachable store every field is empty.

`report.md` has one section per store (insights, recommendations, the pressure score with its
factors, where each value came from, which policy pages were read, changes since the last scan,
featured products) and a comparison table. `business_report.md` summarises across the stores:
platforms, price ranges, shipping and return terms, a feature matrix, what the data shows,
what to compare against, and how the data was collected.

Reports produced by `scripts/demo.py` from the fixture stores: [docs/sample/](docs/sample/report.md)
(English) and [docs/sample/zh/](docs/sample/zh/report.md) (Chinese). Reports from a real store:
[docs/sample/real/allbirds/](docs/sample/real/allbirds/report.md), one scan of a public storefront
(allbirds.com on 2026-10-12, default settings), with the prices it showed that day. It is the
corpus store that scored 10 of 10 (tied with deathwishcoffee, whose free-returns value is "not
stated"); the reports are the tool's output as it was, including its rough edges (product titles
that run colour and price together, see [docs/observations.md](docs/observations.md) section 12).

## What "AI" means here

Only the optional `--ai` step uses a model: a language model running locally under Ollama writes
insight and recommendation text. Everything else is rules: regular expressions, HTML selectors and
fixed thresholds.

The competitive pressure score in `report.md` is a fixed rubric, not a model. Each of six factors
gets 0 to 10 by a fixed rule, and the score is the weighted sum rounded and clamped to 1-10.
`report.md` prints every factor's inputs, rule and score.

| factor | weight | rule (summary) |
|---|---|---|
| platform maturity | 0.15 | Shopify 9, BigCommerce 8, WooCommerce / Magento 7, Squarespace 6, Wix 5, unknown 4 |
| price competitiveness | 0.20 | median price under $25: 9, under $50: 7, under $100: 5, otherwise 3 |
| marketing tactics | 0.20 | 1, plus popup 2, email capture 2, loyalty 2, referral 2, announcement bar 1 |
| trust signals | 0.15 | 1, plus review platform 3, reviews over 100: 2 (any: 1), buy-now-pay-later 2, 3+ payment methods 1 |
| shipping offer | 0.15 | free shipping on everything 9, threshold under $50: 7, under $100: 5, otherwise 3 |
| brand signals | 0.15 | 5, plus more than 500 reviews 2, loyalty 1, 3+ categories 1 |

An unknown input scores 5 for price and shipping and counts as absent elsewhere.

## Development

```powershell
venv\Scripts\python -m pip install pytest
venv\Scripts\python -m pytest -q
```

- **Tests** (`tests/`, about a minute) run against local servers only; no test touches the
  internet. The fixture run with `--render-js` runs only with `ECI_TEST_RENDER_JS=1` (it needs
  `playwright install chromium`).
- **Fixture stores**: `tests/fixtures/stores/<store>/` holds the pages and `fixtures.json` the true
  values; `python tests/fixtures/stores/server.py` serves all three on 127.0.0.1.
- **`scripts/score_fixtures.py`** runs `main.py` on each fixture store and scores every field
  against `fixtures.json`, with the rule that produced each value. The test suite fails if any
  field stops matching.
- **`scripts/real_corpus.py`** (`run` / `score`) runs the tool once per real store and scores it
  against `docs/real-corpus/<store>.json`. `run` visits real websites; see
  [docs/real-corpus/README.md](docs/real-corpus/README.md) for how the ground truth is read (by
  hand, before the tool's output for that store is looked at).
- **Run log**: every run writes `logs/run_<id>.jsonl`, one JSON event per stage, fetch and field,
  including the rule or selector that produced each value and every exception that was handled.
  `python scripts/failure_report.py` summarises the newest log.
- **Pre-commit hook**: `python scripts/install-hooks.py` installs a hook that runs the full test
  suite and refuses the commit if a test fails. CI runs the same suite on Ubuntu and Windows
  (`.github/workflows/ci.yml`).
- Change history and findings: [docs/phase2.md](docs/phase2.md), [docs/phase3.md](docs/phase3.md),
  [docs/phase4.md](docs/phase4.md), [docs/phase5.md](docs/phase5.md),
  [docs/observations.md](docs/observations.md).

## Limitations

- Without `--render-js` only the HTML the server sends is read; stores that draw prices with
  JavaScript report no products (one of the eight real stores).
- Each store is sampled: at most 20 pages and 50 products by default, and at most 10 products from
  any one collection page (the homepage's product cards and Shopify's products.json count as one
  collection each). The price range is over that sample, not the catalogue; `report.md` and
  `business_report.md` say how many products came from how many collections.
- Extraction is pattern-based and written for English-language pages. A phrasing the patterns do
  not know is missed (one store's loyalty program is a "membership" with none of the usual
  words). Free returns are reported only when a page says who pays for them, and email capture
  is unknown when only a sign-up script (Klaviyo and similar) is loaded; both are empty cells
  then, not "no".
- Price rules in the pressure score assume US dollars.
- Stores behind strong bot protection end as blocked. The tool does not log in, add to cart or
  check out.
- A store skipped because of robots.txt is not in the reports (the console and the run log say
  why).
- The `--ai` text is always in Chinese and needs a local Ollama install; the step has been tested
  only against a fake Ollama client.

## License

MIT, see [LICENSE](LICENSE). [NOTICE.md](NOTICE.md) covers trademarks and fixtures.
