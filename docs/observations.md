# Observations (Phase 1 baseline)

Everything below was measured against the local fixture stores (`tests/fixtures/stores/`) on
127.0.0.1, or read from the code at this commit. No real site was fetched. Reproduce with:

```
python scripts/score_fixtures.py --baseline-dir docs/baseline
python scripts/failure_report.py docs/baseline/logs
```

Evidence lives in `docs/baseline/`: `fixture_scores.md` / `.json` (field-by-field score with the
obs source of every value), `failure_report.md`, and the four run logs under `logs/`.
Line numbers refer to this commit (after instrumentation).

## 1. The outside run, checked

The brief listed six results from an outside run against a `shopify_basic` store. Five
reproduce on our fixture; one does not.

| # | Outside result | Here | Code that produces it |
|---|---|---|---|
| 1 | `price_max` 24 (missed $39) | **Not reproduced.** Ours: 39, both products parsed from the card grid on `/collections/all`. | See 1.1. |
| 2 | `has_discounts` False | **Reproduced** (both stores). | `modules/product_extractor.py:588-593`, `:616` (1.2) |
| 3 | `loyalty` True | **Reproduced.** | `modules/promo_extractor.py:367` (1.3) |
| 4 | Google Analytics detected | **Reproduced.** | `modules/promo_extractor.py:532-534` (1.4) |
| 5 | Invented brand positioning, in Chinese, under `--lang en` | **Reproduced** (both stores). | `main.py:224-286`, `modules/report_writer.py:638` (1.5) |
| 6 | Business report says "multiple players" with one site | **Reproduced** (every run, including the blocked store). | `modules/business_report.py:480-481` (1.6) |

### 1.1 price_max 24: not reproduced, and the paths that would produce it

In our run the hoodie card yields 39 (`price via '.price' text 'Regular price$39.00 USDRegular
price$49.00 USDSale price$39.00 USD' -> 39.0`), so `price_max` is right. The outside fixture must
have differed. The code only sees a product if it is on a card grid at one of the guessed
collection URLs, so two paths give `price_max = 24` with a $39 product in the store:

- **The $39 product is not on a guessed collection page.** Product pages are never fetched:
  `get_priority_pages()` (`modules/url_utils.py:316-350`) has no `/products/<handle>` paths, and the
  homepage link crawl is skipped because the 22 guessed paths already fill `max_pages=20`
  (`modules/page_discovery.py:90`; logged as `discovery` / `degraded`: *"22 guessed/sitemap pages
  already >= max_pages=20"*). The homepage itself is excluded from product extraction
  (`main.py:680`). Our server log for `shopify_basic` shows **zero** requests to `/products/...`.
  A store whose collection page lives at, say, `/collections/frontpage` gets no products at all,
  and then the homepage-HTML fallback (`modules/price_extractor.py:36`) decides the range from
  whatever its first non-empty method finds.
- **The $39 card's price element did not parse.** `_extract_price_from_element()`
  (`product_extractor.py:534`) returns `None` when no selector in its list has a `$` in its text
  and the card text has no `$N`; `calculate_price_stats()` (`:711`) then skips that product.

### 1.2 has_discounts False

`has_discounts` is `any(p.price.is_on_sale)` (main.py, `_note_price_stats` logs the inputs);
`is_on_sale = compare_price > current_price` (`product_extractor.py:616`).

- **Shopify (Dawn) cards:** the compare-at list (`:588-593`) tries `.price-item--regular` before `s`
  and `del`. Dawn renders the current price in `.price__regular .price-item--regular` first, so the
  compare-at price read is `$39.00`, equal to the current price -> not on sale. Log:
  `compare via '.price-item--regular' text '$39.00 USD' -> 39.0`.
- **WooCommerce cards:** the price selector matches the whole `span.price` block, whose text starts
  with the struck-through price: `'$60.00Original price was: $60.00.$48.00Current price is:
  $48.00.' -> 60.0`; compare via `del` -> 60.0. Result: `price_min` 35 / `price_max` 60 /
  `price_median` 47.5 instead of 28 / 48 / 38, and no discount detected on a store where every
  product is 20% off.

### 1.3 loyalty True

`_detect_loyalty()` (`promo_extractor.py:356`) returns True if `'yotpo'` appears anywhere in the raw
HTML (`loyalty_platforms`, `:367`). Yotpo here is the **reviews** widget. The keyword list
(`:128-131`) is also matched as substrings of the page text: `member`, `points`, `vip`,
`rewards`. Log: `has_loyalty True <- regex: loyalty platform substring 'yotpo' in raw html`.

### 1.4 Google Analytics detected

`ga_patterns` includes `r'G-[A-Z0-9]+'` (`promo_extractor.py:532`) and the search uses
`re.IGNORECASE` (`:534`), so it matches any `g-` followed by a letter or digit. On
`shopify_basic` it matched `g-link` inside the CSS class `header__heading-link`. The ID regex
below it is case-sensitive, so the pixel is reported with no ID. Any page with `shipping-`,
`loading-`, `heading-`, `img-` in its markup is reported as running Google Analytics.

### 1.5 Chinese brand positioning under --lang en

`generate_brand_description_zh()` (`main.py:224-286`) looks up substrings of
`meta + hero + tagline + html[:5000]`, lower-cased, in fixed keyword tables, and always returns
Chinese. The first 5000 characters of HTML are mostly `<head>` markup:

- shopify_basic: `style` in `rel="stylesheet"` -> 时尚服饰 (fashion); `hip` in `shipping` -> 年轻消费者
  (young consumers); `men` -> 男性 (men). Result "时尚服饰品牌，面向年轻消费者、男性" for a cotton
  basics store whose copy mentions none of these.
- woocommerce_promo: `style` -> 时尚服饰, `hip` -> 年轻消费者, `her` -> 女性 (women).

The value goes to `brand_positioning` in report.csv (`report_writer.py:638`) and to the comparison
table in report.md (`:501`). `InsightGenerator` (`modules/insight_generator.py:31-33`) accepts a
`language` argument and never reads it, so the key insights, recommendations and evidence lists in
report.md are Chinese under `--lang en` as well (`report_md_insights_chinese_under_lang_en: True`
in every run).

### 1.6 "Multiple players" with one site

`_generate_swot_analysis()` appends "Platform Concentration: Heavy reliance on Shopify ecosystem"
and "Price Competition: Multiple players in similar price ranges may pressure margins"
unconditionally (`business_report.py:480-481`). The appendix always says "Automated web scraping
respecting robots.txt" and "AI-powered insight generation using Qwen2.5 LLM" (`:574-575`), also
when `--ai` was not given, when Ollama was unreachable, and when `--ignore-robots` was set. All
four baseline runs (one site each, no AI) contain all four sentences, including the WooCommerce
run ("Heavy reliance on Shopify") and the blocked run (no data at all).

## 2. Guessed priority pages: what they cost

`get_priority_pages()` (`modules/url_utils.py:316-350`) yields 22 paths. With `max_pages=20` the
two contact paths are cut, the homepage is skipped, and 19 are fetched, each behind the 1.5 s
per-host delay (`modules/models.py:333`, enforced in `RateLimiter.wait`, `http_client.py:71`).

| store | pages that exist (excl. robots.txt) | guessed paths fetched | 404 | time spent on the 404s | run wall time |
|---|---|---|---|---|---|
| shopify_basic | 6 | 19 | 16 | 24.0 s | 38.0 s |
| woocommerce_promo | 6 | 19 | 18 | 27.0 s | 36.6 s |

On top of that every run fetches the homepage twice (`main.py:493`, only to read headers), three
guessed sitemap URLs (all 404) and, for Shopify, `/products.json` (404 here). shopify_basic: 26
requests for a 6-page store, 20 of them 404. The time is almost entirely the fixed delay (the
fixture answers in ~1 ms): `fetch` p50 is ~1.5 s in `failure_report.md`.

What the guesses miss matters more than what they cost: none of the product pages of either
store, and neither WooCommerce policy page (`/shipping-policy`, `/refund_returns` are not in the
list), were ever requested. That is why woocommerce_promo has `return_days` null and
`free_returns` null, and why both stores' free-shipping thresholds come from homepage text, not
from a policy page.

## 3. Other findings from the baseline

- **A site that could not be loaded is reported as if it were analysed.** On the blocked store,
  `analyze_site` returns a default `SiteIntelligence` (`main.py:473`), which is saved, appended to
  the results and written to all three reports with `has_popup/has_email_capture/has_loyalty/
  has_referral/has_discounts = False` and `currency = USD` (6 of 16 fields scored as mismatches:
  definite answers about a site never seen). The only hint is `errors` in the snapshot and a
  "采集警告" line in report.md. The business report counts it as a competitor.
- **robots.txt behind a bot wall means "everything allowed".** The blocked store answers 403 for
  `/robots.txt`; `_fetch_robots()` (`robots_checker.py:40-79`) treats any non-200 as "no rules".
  *Phase 2 (Batch 6), left as is:* for 4xx this is what RFC 9309 specifies (section 2.3.1.3,
  "Unavailable" status: a crawler MAY access any resources), so a 403 on `/robots.txt` correctly
  means "no robots.txt". The RFC treats 5xx and network errors differently ("Unreachable":
  assume complete disallow); the code still treats those as "allowed" too, which this note does
  not change.
- **Fallback chain on the blocked store** (owner decision A3; chains from the obs log):
  default run `requests(403) -> cloudscraper(403)`; `--render-js` run `browser(403, 2798 B
  rendered challenge page) -> cloudscraper(403)`. The browser engine was Playwright driving the
  installed Chrome (`channel="chrome"`); patchright is not installed (it is commented out in
  requirements.txt), so the Playwright stealth init script ran. Chrome also requested the challenge
  script and `/favicon.ico` (both 403 from the fixture). cloudscraper sent
  `Mozilla/5.0 (Windows; U; Windows NT 5.2; ...)` as its User-Agent, not the configured one.
  There is no `requests -> cloudscraper -> browser` order in the code (see "brief" section below).
- **Change detection is one scan late** (`--monitor`). `compute_changes()` is called before the
  current scan is saved (`main.py:1128` vs `:1140`) and reads the second-newest stored row
  (`snapshot_store.py:155`, `OFFSET 1`). Checked directly against `SnapshotStore`: scan 2 with
  `price_max` 20 -> 99 reports **nothing**; scan 3, identical to scan 2, reports
  "最高价从 $20.0 变为 $99.0".
- **Hosts without a public suffix collapse to one domain.** `extract_domain()`
  (`url_utils.py:91-116`) returns `127.0.0.1` for every port, so snapshot history, change reports
  and report sections keyed by `domain` merge all local stores. The scorer runs one store per
  process and per SQLite file to avoid this. The same applies to `localhost`, intranet hosts and
  bare IPs.
- **The AI stage reads fields that do not exist.** `ChineseInsightGenerator._build_prompt()` and
  `ThreatScorer` read `free_shipping_threshold`, `return_days`, `free_returns` from the top level of
  `intel.to_dict()`, where they never are (they are nested under `shipping_policy` /
  `return_policy`). The prompt always says N/A and the threat score's shipping factor is always 5.
  `AIConfig.ollama_host` is never passed to the `ollama` client. Not exercised in the baseline
  (no Ollama), read from code.
- **Shopify `/products.json` prices.** Real `/products.json` serves prices as strings
  (`"39.00"`). `_parse_shopify_product()` (`product_extractor.py:273`) only reads
  `compare_at_price` when it is numeric (`:312`), but computes `is_on_sale` by comparing the
  strings (`:313`). Numeric prices over 100 are treated as cents and divided by 100 (`:306`), so a
  numeric price of 150 dollars becomes 1.50 while 99 cents stays 99. Read from code; our fixture
  does not serve `/products.json`.
- **429 handling is unreachable.** urllib3 `Retry(status_forcelist=[429, 500, ...])`
  (`http_client.py:163`) retries and then raises, so the `status_code == 429` branch (`:479`) never
  runs; the result is `Request error: ...`.
- **config.yaml is mostly ignored.** CLI defaults win over `timeout`, `max_products`, `max_pages`
  (`main.py:1021-1023`); `rate_limit_delay`, `user_agent`, `language` and the rest of
  config.example.yaml are read by nothing (logged per run as `config_keys_ignored`).
- **The first test run made a network call.** `tldextract` downloaded the public suffix list from
  publicsuffix.org during the first `pytest` run of this session (cache written at 18:49 under
  `~/.cache/python-tldextract/`). Later runs used the cache. Any fresh environment will do the same
  on first use of `extract_domain()`.
- **Unused machinery that reports describe as active:** `policy_evidence.py` (evidence ladder,
  level 4 "blocked by robots.txt") is never called; `RobotsChecker.blocked_urls`,
  `get_crawl_delay()`, `HttpClient.head()`, `PolicyExtractor.extract_policy_links_from_footer()`,
  `SnapshotStore.cache_page()`, `PricingPredictor.save_model()` are never called;
  `robots_checker.py:90` is unreachable (after a `return`).
- **Sitemap fetch order is not deterministic.** `_parse_sitemap()` iterates
  `list(set(sitemap_urls + common_sitemaps))` (`page_discovery.py:140`); string hashing is
  randomised per process, so the three sitemap requests come in a different order from run to run.
  Same requests, different order; the reports are unaffected unless a sitemap exists and the
  `max_pages * 2` cut-off is reached.
- **Provenance caveat.** The obs `field` event credits the candidate the pipeline assigned
  (`obs.apply`) or, failing that, the most recent candidate with an equal value. Two extractors
  producing the same value on the same page can still be credited to the later one.

### Behaviour check: instrumentation changed no output

The four fixture runs were repeated with the original v16 sources (`git stash` of `main.py` and
`modules/`, then restored) and compared with the instrumented runs after normalising ports,
timestamps and dates:

| run | report.csv | report.md | business_report.md | requests made |
|---|---|---|---|---|
| shopify_basic | identical | identical | identical | identical sequence (26) |
| woocommerce_promo | identical | identical | identical | same 25 requests; sitemap order differs (see above) |
| blocked | identical | identical | identical | identical sequence (3) |
| blocked_render_js | identical | identical | identical | identical sequence (5) |

The only visible difference is one extra console line, `Run log: logs/run_<run_id>.jsonl`, and
the `logs/` directory.

## 4. Things in the brief that turned out different

- The repo has six zips, but they are v10, v12, v13, v14, v15, v16 (no v11).
- The zip's `README.md` collided with the repo's landing-page README; the root README was kept
  and the zip's copy is `docs/history/README_v16_package.md`. The zip also contains an empty
  directory literally named `{modules,tests,data}` (a shell brace-expansion accident), not unpacked.
- `V15_RELEASE_NOTES .md` had a trailing space in its name; it is `docs/history/V15_RELEASE_NOTES.md`.
- `architecture-clean.svg` (repo root) was not in the move list and was left where it is.
- The "~22 guessed priority pages" are exactly 22; 20 survive `max_pages`, 19 are fetched.
- Owner decision A3 describes the fallback chain as `requests 403 -> cloudscraper -> browser`. The
  code has two chains: `requests -(403 only)-> cloudscraper` by default, and
  `browser -(403 or error)-> cloudscraper -> placeholder (PROTECTED_SITES only)` with
  `--render-js`. The browser never runs after cloudscraper. The blocked fixture is therefore run
  twice (with and without `--render-js`) to exercise both.
- The brief's stage order (`discovery` before `platform`, `promos/trust/categories` after
  products, `snapshot` before `change diff`) is not the code's order; `docs/pipeline-stages.md`
  documents the actual order.
- The `blocked` store answers 403 for every path including `/robots.txt`, as "every page returns
  403" requires; it therefore has no robots.txt, homepage or product pages of its own, only the
  challenge body.
- The outside `price_max 24` result did not reproduce (section 1.1).

## 5. Swallowed exceptions (every except handler)

Each handler now calls `obs.swallowed(where, error_type, fallback)` (or is marked
`# obs: import-time` when it runs at import, before a run log exists; those are reported later
from `HttpClient.__init__`, `AIAnalyzer.__init__` or `main()`). `tests/test_obs.py` fails if a
handler without an `obs.*` call is added. Behaviour is unchanged: each handler does what it did
before, plus the log call. "classified from exception" means the error_type is derived from the
exception class at run time (`obs.classify_exception`).

| location (except line) | function | catches | error_type | what happens instead |
|---|---|---|---|---|
| `main.py:176` | `extract_brand_info` | `Exception` | parse | next hero selector |
| `main.py:208` | `extract_brand_info` | `Exception` | parse | next tagline selector |
| `main.py:307` | `extract_categories` | `Exception` | parse | legacy nav selectors |
| `main.py:401` | `extract_categories` | `Exception` | parse | next nav selector |
| `main.py:559` | `analyze_site` | `bare except` | parse | review count unchanged |
| `main.py:580` | `analyze_site` | `bare except` | parse | payment methods unchanged |
| `main.py:660` | `analyze_site` | `json.JSONDecodeError` | parse | no products.json products |
| `main.py:667` | `analyze_site` | `Exception` | classified from exception | HTML pages only |
| `main.py:1053` | `main` | `ImportError` | unknown | AI stage skipped |
| `main.py:1167` | `main` | `Exception` | classified from exception | report without AI sections |
| `main.py:1182` | `main` | `Exception` | classified from exception | site dropped from the report |
| `main.py:1224` | `main` | `Exception` | classified from exception | no business_report.md |
| `modules/__init__.py:35` | `<module>` | `ImportError` | import time | obs: import-time, reported by main.py in the load stage |
| `modules/ai_analyzer.py:28` | `<module>` | `ImportError` | import time | obs: import-time, reported by AIAnalyzer.__init__ |
| `modules/ai_analyzer.py:36` | `<module>` | `ImportError` | import time | obs: import-time, reported by AIAnalyzer.__init__ |
| `modules/ai_analyzer.py:43` | `<module>` | `ImportError` | import time | obs: import-time, reported by AIAnalyzer.__init__ |
| `modules/ai_analyzer.py:131` | `is_available` | `Exception` | external_api | AI unavailable |
| `modules/ai_analyzer.py:171` | `generate` | `Exception` | external_api | None |
| `modules/ai_analyzer.py:427` | `_load_or_create_model` | `Exception` | parse | retrain on synthetic data |
| `modules/http_client.py:38` | `<module>` | `ImportError` | import time | obs: import-time, reported by HttpClient.__init__ |
| `modules/http_client.py:46` | `<module>` | `ImportError` | import time | obs: import-time, reported by HttpClient.__init__ |
| `modules/http_client.py:55` | `<module>` | `ImportError` | import time | obs: import-time, reported by HttpClient.__init__ |
| `modules/http_client.py:149` | `_create_cloudscraper` | `Exception` | classified from exception | cloudscraper_session=None |
| `modules/http_client.py:225` | `_init_playwright` | `Exception` | classified from exception | bundled Chromium |
| `modules/http_client.py:410` | `_fetch_with_cloudscraper` | `Exception` | classified from exception | returned (None, 0, {}, error) |
| `modules/http_client.py:489` | `_fetch_with_requests` | `requests.exceptions.SSLError` | http | retry with verify=False |
| `modules/http_client.py:489` | `_fetch_with_requests` | `requests.exceptions.SSLError` | http | returned (None, 0, {}, error) |
| `modules/http_client.py:503` | `_fetch_with_requests` | `Exception` | http | returned (None, 0, {}, error) |
| `modules/http_client.py:508` | `_fetch_with_requests` | `requests.exceptions.Timeout` | timeout | returned (None, 0, {}, error) |
| `modules/http_client.py:513` | `_fetch_with_requests` | `requests.exceptions.ConnectionError` | http | returned (None, 0, {}, error) |
| `modules/http_client.py:518` | `_fetch_with_requests` | `requests.exceptions.RequestException` | http | returned (None, 0, {}, error) |
| `modules/http_client.py:548` | `_fetch_with_playwright` | `bare except` | classified from exception | wait 2s and read the page anyway |
| `modules/http_client.py:565` | `_fetch_with_playwright` | `PlaywrightTimeout` | timeout | returned (None, 0, {}, error) |
| `modules/http_client.py:569` | `_fetch_with_playwright` | `Exception` | http | plain requests fetch |
| `modules/http_client.py:569` | `_fetch_with_playwright` | `Exception` | classified from exception | returned (None, 0, {}, error) |
| `modules/http_client.py:608` | `fetch_and_parse` | `Exception` | parse | html.parser |
| `modules/http_client.py:615` | `fetch_and_parse` | `Exception` | parse | returned (None, status, error) |
| `modules/http_client.py:637` | `head` | `Exception` | classified from exception | returned (0, {}, error) |
| `modules/page_discovery.py:196` | `_fetch_sitemap` | `ET.ParseError` | parse | pages so far |
| `modules/page_discovery.py:200` | `_fetch_sitemap` | `Exception` | classified from exception | pages so far |
| `modules/policy_extractor.py:461` | `extract_policies_from_homepage_js` | `bare except` | parse | ignore sddShippingOptions |
| `modules/price_extractor.py:194` | `_extract_shopify_search_settings` | `ValueError` | parse | continue |
| `modules/price_extractor.py:211` | `_extract_shopify_search_settings` | `ValueError` | parse | continue |
| `modules/price_extractor.py:254` | `_extract_window_products` | `json.JSONDecodeError` | parse | regex over the JS text |
| `modules/price_extractor.py:254` | `_extract_window_products` | `json.JSONDecodeError` | parse | continue |
| `modules/price_extractor.py:262` | `_extract_window_products` | `ValueError` | parse | continue |
| `modules/price_extractor.py:265` | `_extract_window_products` | `Exception` | parse | continue |
| `modules/price_extractor.py:290` | `_extract_prices_from_data` | `ValueError` | parse | pass |
| `modules/price_extractor.py:357` | `_extract_jsonld_prices` | `(json.JSONDecodeError, Exception)` | parse | skip this ld+json block |
| `modules/price_extractor.py:377` | `_parse_offer_price` | `ValueError` | parse | pass |
| `modules/price_extractor.py:408` | `_extract_data_attribute_prices` | `ValueError` | parse | continue |
| `modules/price_extractor.py:450` | `_extract_inline_js_prices` | `ValueError` | parse | continue |
| `modules/price_extractor.py:480` | `_extract_meta_prices` | `ValueError` | parse | continue |
| `modules/price_extractor.py:533` | `_extract_html_price_text` | `ValueError` | parse | continue |
| `modules/product_extractor.py:140` | `_extract_shopify` | `(json.JSONDecodeError, Exception)` | parse | skip this application/json script |
| `modules/product_extractor.py:168` | `_extract_shopify` | `bare except` | parse | ignore inline product array |
| `modules/product_extractor.py:191` | `_extract_shopify` | `bare except` | parse | ignore this ld+json script |
| `modules/product_extractor.py:267` | `_parse_structured_data_product` | `Exception` | parse | None |
| `modules/product_extractor.py:360` | `_parse_shopify_product` | `Exception` | parse | None |
| `modules/product_extractor.py:528` | `_parse_product_card` | `Exception` | parse | None |
| `modules/product_extractor.py:633` | `_extract_price_from_element` | `Exception` | parse | None (no price) |
| `modules/product_extractor.py:682` | `_parse_price_string` | `ValueError` | parse | pass |
| `modules/robots_checker.py:74` | `_fetch_robots` | `Exception` | classified from exception | treat every URL as allowed |
| `modules/robots_checker.py:126` | `is_allowed` | `Exception` | parse | allowed |
| `modules/robots_checker.py:163` | `get_crawl_delay` | `Exception` | parse | None |
| `modules/robots_checker.py:194` | `get_sitemaps` | `Exception` | parse | [] |
| `modules/trust_extractor.py:174` | `_detect_review_platform` | `bare except` | parse | review_count unchanged |
| `modules/trust_extractor.py:273` | `_detect_payment_methods` | `bare except` | parse | apple pay JSON ignored |
| `modules/url_utils.py:84` | `normalize_url` | `Exception` | input_invalid | URL returned as given |
| `modules/url_utils.py:111` | `extract_domain` | `Exception` | input_invalid | netloc parse |
| `modules/url_utils.py:131` | `extract_full_domain` | `Exception` | input_invalid | url |
| `modules/url_utils.py:231` | `is_valid_url` | `Exception` | input_invalid | False |

## 6. Silent fallbacks without an exception

Places where the code quietly substitutes a default or a weaker source. Each now emits an
`obs.degraded(...)` event (`event` = `skip` or `fail`, `context.degraded = true`).

| location | function | condition | error_type | what happens instead |
|---|---|---|---|---|
| `main.py:305` | `extract_categories` | category_extractor found nothing | parse | legacy nav selectors |
| `main.py:467` | `analyze_site` | homepage fetch failed; analysis stops here | obs.classify_fetch(status, error) or 'http' | SiteIntelligence with defaults is still saved and reported (and AI-scored with --ai) |
| `main.py:482` | `analyze_site` | homepage is the PROTECTED_SITES placeholder | blocked | continue extracting from placeholder HTML |
| `main.py:664` | `analyze_site` | f'products.json unavailable: {error}' | obs.classify_fetch(status, error) or 'http' | HTML pages only |
| `main.py:798` | `analyze_site` | no products extracted from any page | parse | homepage JS price fallback |
| `main.py:830` | `analyze_site` | no shipping policy parsed from any page | parse | ad-hoc ShippingPolicy from homepage promo threshold, regions=['United States'] |
| `main.py:1008` | `main` | ai_analyzer import failed | unknown | AI_AVAILABLE=False |
| `main.py:1011` | `main` | f'config file {config!r} not found' | input_invalid | built-in defaults |
| `main.py:1047` | `main` | --ai given but Ollama/model unavailable | external_api | AI stage skipped for every site |
| `modules/ai_analyzer.py:124` | `is_available` | f'model {self.model} not in ollama.list()' | external_api | AI unavailable |
| `modules/ai_analyzer.py:205` | `generate_insights` | Ollama unavailable | external_api | template insights |
| `modules/ai_analyzer.py:215` | `generate_insights` | empty LLM response | external_api | template insights |
| `modules/ai_analyzer.py:355` | `analyze_positioning` | Ollama unavailable | external_api | 'AI分析不可用' string |
| `modules/ai_analyzer.py:501` | `predict_optimal_price` | no sklearn model | unknown | competitor_price * 0.9 rule |
| `modules/http_client.py:131` | `__init__` | patchright not importable | unknown | f'browser engine = {BROWSER_ENGINE}' |
| `modules/http_client.py:135` | `__init__` | cloudscraper not importable | unknown | no cloudscraper branch |
| `modules/http_client.py:434` | `_fetch_protected_site` | PROTECTED_SITES match: synthetic placeholder HTML returned with status 200 | blocked | placeholder page |
| `modules/http_client.py:599` | `fetch_and_parse` | empty body with no error | http | returned (None, status, 'Empty response') |
| `modules/page_discovery.py:98` | `discover` | f'{len(discovered)} guessed/sitemap pages already >= max_pages={self.config.max_pages}' | unknown | homepage links are never crawled |
| `modules/page_discovery.py:155` | `_fetch_sitemap` | invalid sitemap URL | input_invalid | [] |
| `modules/page_discovery.py:164` | `_fetch_sitemap` | error or 'empty sitemap body' | obs.classify_fetch(status, error) or 'http' | [] |
| `modules/page_discovery.py:219` | `_crawl_links` | error or 'no soup' | obs.classify_fetch(status, error) or 'http' | no crawled links |
| `modules/product_extractor.py:91` | `extract_from_page` | f'{self.platform.value} extractor found no products' | parse | _extract_generic |
| `modules/product_extractor.py:188` | `_extract_shopify` | JSON-LD @graph is not searched for Product nodes | parse | ignored |
| `modules/robots_checker.py:67` | `_fetch_robots` | f'robots.txt answered {response.status_code}' | obs.classify_fetch(response.status_code, f'status {response.status_code}') or 'http' | treat every URL as allowed |
| `modules/robots_checker.py:181` | `get_sitemaps` | no parsed robots.txt | parse | guess /sitemap.xml and /sitemap_index.xml |
| `modules/url_utils.py:107` | `extract_domain` | no public suffix (IP address or local host): port and subdomain dropped | input_invalid | f'domain={extracted.domain!r}' |

Value-level defaults are not listed as rows: every report field is logged at the end of each site
as a `field` event, and a field whose value no extractor produced carries `source: "default"`
(for example `has_loyalty: False` on the blocked store). `scripts/score_fixtures.py` shows that
source next to each scored value.
