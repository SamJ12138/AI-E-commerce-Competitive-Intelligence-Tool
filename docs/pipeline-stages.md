# Pipeline stages

From `sites.txt` to `report.md`, `report.csv` and `business_report.md`, as the code runs today
(Phase 1 snapshot, branch `restructure`). Line numbers refer to this commit. The `obs stage`
column is the `stage` value the structured run log (`modules/obs.py`, `logs/run_<run_id>.jsonl`)
uses for that step.

## Actual order

The order is not the one the components suggest. Promotions, trust signals and categories are
read **from the homepage only**, before any other page is discovered; the change diff runs
**before** the snapshot is written; AI runs **after** the snapshot (so AI output is never stored).

```
main()                                                    main.py:974
 ├─ load        config.yaml + CLI -> Config; sites.txt -> URLs
 └─ per site (sequential)
     ├─ robots      robots.txt for the homepage (site skipped if disallowed)
     └─ analyze_site()                                    main.py:422
         ├─ fetch_homepage   fetch_and_parse(homepage)     -> on error: return defaults (see failure modes)
         ├─ platform         fetch(homepage) AGAIN for headers, detect_platform()
         ├─ brand            extract_brand_info() + generate_brand_description_zh()
         ├─ categories       extract_categories() (homepage nav)
         ├─ promos           extract_promotions() (homepage only)
         ├─ trust            extract_trust_signals() (homepage only) + Shopify supplement
         ├─ discovery        discover_pages(): 22 guessed paths, sitemaps, (link crawl)
         ├─ products         Shopify /products.json; per discovered page: fetch + extract_products()
         │                   + extract_policies() on policy-like URLs; price stats; JS price fallback
         └─ policies         shipping-policy fallbacks; homepage-JS policy fallback
     ├─ change_diff  (--monitor only) compute_changes() against the stored history
     ├─ snapshot     save_snapshot() into SQLite
     └─ ai           (--ai and Ollama reachable) Ollama insights + positioning, pricing model, threat score
 └─ report      report.md + report.csv (ReportWriter), business_report.md (BusinessReportGenerator)
```

`fetch` is not a step of its own: every HTTP request made through `HttpClient.fetch()` is logged as
one `fetch` event (url, status, `served_by`, bytes, branch chain, rate-limit wait) with
`caller_stage` naming the step that asked for it.

## Stages

### load
- **Owner:** `main()` main.py:974, `load_config()` main.py:64, `load_sites()` main.py:72,
  `normalize_url()` / `deduplicate_urls()` modules/url_utils.py:18 / :183.
- **Input:** CLI flags, optional `--config` YAML, `sites.txt` (one URL per line, `#` comments).
- **Output:** `Config` (modules/models.py:323) and a list of normalized, de-duplicated URLs.
- **Failure modes:**
  - Missing/empty sites file -> red console line, `sys.exit(1)` (`load` fail, `input_invalid`).
  - `--config` path that does not exist is silently ignored (`load_config` returns `{}`).
  - `timeout`, `max_products`, `max_pages` from config.yaml never apply: the CLI defaults are
    truthy, so `timeout or config_data.get(...)` always takes the CLI value (main.py:1021-1023).
  - config keys other than `render_js`, `ignore_robots`, `timeout`, `max_products`, `max_pages`,
    `db_path` are read by nothing (`rate_limit_delay`, `user_agent`, `language`, `output_dir`,
    `sites_file`, `page_priority`, `category_keywords` in config.example.yaml).
  - URLs without a scheme get `https://`; malformed URLs pass through unchanged.

### robots
- **Owner:** `RobotsChecker` modules/robots_checker.py:21 (`is_allowed` :92, `_fetch_robots` :40).
- **Input:** a URL; `config.ignore_robots`.
- **Output:** allow/deny, cached per `netloc`. Used once per site by `main()` and for every
  candidate URL in discovery.
- **Failure modes:**
  - robots.txt is fetched with a bare `requests.get` (no rate limit, no retry, timeout 10 s), not
    through `HttpClient`.
  - Any non-200 answer (404, 403 from a bot wall, 5xx) or exception => every URL is treated as
    allowed (`robots` fail/degraded, `treat every URL as allowed`).
  - `--ignore-robots` short-circuits `is_allowed()` to `True`.
  - Rules are evaluated for user agent `*`, not the tool's UA; `Crawl-delay` is parsed by
    `get_crawl_delay()` (:142) but nothing calls it.
  - Blocked URLs are collected in `blocked_urls` but nothing reads them (no report shows them,
    evidence level 4 is never produced).

### fetch (HttpClient)
- **Owner:** `HttpClient.fetch()` modules/http_client.py:292; branches `_fetch_with_requests` :456,
  `_fetch_with_playwright` :523 (patchright if importable, else playwright), `_fetch_with_cloudscraper`
  :387, `_fetch_protected_site` :421; `fetch_and_parse()` :582 wraps it with BeautifulSoup (lxml).
- **Input:** URL, `render_js` flag.
- **Output:** `(html, status, headers, error)`; `fetch_and_parse` returns `(soup, status, error)`.
- **Branches** (logged as `chain` and `served_by`):
  - default: `requests` (urllib3 Retry: 3 retries on 429/5xx, backoff 1 s) -> on **403 only**
    -> `cloudscraper`.
  - `--render-js`: `browser` -> on 403 or any error -> `cloudscraper` -> if that fails and the
    domain is in `PROTECTED_SITES` (:103: lululemon, nike, adidas) -> `placeholder` (synthetic HTML,
    status 200). A browser `net::ERR_*` falls back to a plain requests fetch inside the browser
    branch (`served_by = browser->requests`).
  - There is no `requests -> cloudscraper -> browser` chain: the browser only runs with
    `--render-js`, and then it runs first.
- **Failure modes:**
  - Rate limit 1.5 s per `netloc` (models.py:333), applied before every fetch including 404s.
  - 403 / 404 become error strings. 429 and 500/502/503/504 are retried by urllib3 (3 retries,
    backoff factor 1, http_client.py:163) and then raise `RetryError`, so the `429` branch at :479
    is unreachable and the result is `Request error: ...`; other 4xx raise in
    `raise_for_status()` and also become `Request error: ...`.
  - SSL errors are retried with `verify=False` (silent downgrade).
  - Browser fetch waits a fixed 3 s (or 2 s after a failed `wait_for_selector`) per page.
  - The placeholder path returns status 200 with fabricated HTML; downstream treats it as a page.

### fetch_homepage (start of analyze_site)
- **Owner:** main.py:458-473.
- **Input:** site URL. **Output:** homepage soup + `html_str`.
- **Failure modes:** on any fetch error `analyze_site` returns immediately with a default
  `SiteIntelligence` (`errors` set). `main()` still saves the snapshot, runs AI on it with `--ai`,
  and includes it in all three reports with default values: `has_*` = `False`, `currency` = `USD`,
  platform `Custom/Unknown`. The blocked fixture shows this end to end.

### platform
- **Owner:** `detect_platform()` modules/platform_detector.py:279 -> `PlatformDetector.detect()` :169.
- **Input:** homepage soup, response headers (from a **second** fetch of the homepage, main.py:493:
  one extra request and 1.5 s per site), URL.
- **Output:** `Platform`, confidence (0.6/0.8/0.95 by signal count), signal list.
- **Failure modes:** substring regexes over the whole HTML (`"Shopify"`, `woocommerce`, `Magento`,
  `requirejs`) can fire on text that merely mentions a platform; ties go to the earlier `Platform`
  enum member; no signal => `Custom/Unknown` with confidence 0.

### brand
- **Owner:** `extract_brand_info()` main.py:106, `generate_brand_description_zh()` main.py:224.
- **Input:** homepage soup and HTML.
- **Output:** `brand_name`, `meta_description`, `hero_text`, `brand_description_zh`.
- **Failure modes:** `brand_description_zh` is a keyword lookup over
  `meta + hero + tagline + html[:5000]` (substrings, so `style` matches `stylesheet`, `hip` matches
  `shipping`, `men` matches `women`/`comment`), always written in Chinese, and it is the value of
  the `brand_positioning` column in report.csv and the "Brand Positioning" column in report.md,
  whatever `--lang` says.

### categories
- **Owner:** `extract_categories()` main.py:289 -> `CategoryExtractor` modules/category_extractor.py:19,
  legacy selector list in main.py as fallback.
- **Input:** homepage soup. **Output:** up to 15 category names.
- **Failure modes:** link-text heuristics (`Shop all` becomes `all`); fallback to legacy selectors
  when the module finds nothing or raises.

### promos
- **Owner:** `extract_promotions()` modules/promo_extractor.py:632 (`PromoExtractor` :24).
- **Input:** homepage soup and HTML only.
- **Output:** announcement bar, popup / email capture / loyalty / referral flags, free-shipping
  threshold candidate, discount promotions, social embeds, analytics pixels.
- **Failure modes:** substring and very broad regex detection (see docs/observations.md:
  `G-[A-Z0-9]+` with IGNORECASE matches `g-link`; `yotpo` counts as a loyalty platform;
  `member`, `points`, `vip` as words anywhere in the page text).

### trust
- **Owner:** `extract_trust_signals()` modules/trust_extractor.py:379, plus the Shopify supplement
  in main.py (Judge.me settings, `apple-pay-shop-capabilities`, PayPal meta, free-shipping text,
  promo-slide announcement).
- **Input:** homepage soup and HTML only.
- **Output:** review platform, review count, payment methods, badges, guarantees.
- **Failure modes:** card brands collapse to `Credit Card`; substring matching over HTML + text
  (`discover` matches the word "Discover", `affirm` matches "affirmation").

### discovery
- **Owner:** `discover_pages()` modules/page_discovery.py:255 -> `PageDiscovery.discover()` :48;
  `get_priority_pages()` modules/url_utils.py:316.
- **Input:** homepage URL, robots checker, `max_pages` (20).
- **Output:** list of `(url, page_type)`, sorted home -> collection -> product -> policy -> about ->
  contact, cut to `max_pages`.
- **Failure modes:**
  - 22 guessed paths (`/collections`, `/products`, `/shop`, `/pages/faq`, ... :316-350) are added
    first. Because 22 >= `max_pages`, the homepage link crawl (:90) **never runs** with default
    settings, so product pages and policy pages at non-guessed URLs are never seen.
  - Each guessed path costs a fetch and the 1.5 s delay even when it 404s.
  - Sitemaps: robots.txt `Sitemap:` entries plus three guessed sitemap URLs; XML errors are swallowed.
  - The homepage is fetched a third time inside `_crawl_links` when the crawl does run.

### products (and prices)
- **Owner:** page loop main.py:679-766; `extract_products()` modules/product_extractor.py:689;
  `calculate_price_stats()` :711; Shopify `/products.json` main.py:642-668;
  JS fallback `extract_price_stats_from_html()` modules/price_extractor.py:564.
- **Input:** discovered pages (`pages[:max_pages]`, homepage skipped at main.py:680).
- **Output:** `all_products`, `hero_products` (first 3), `price_min/max/median`, `currency`,
  `has_discounts`, `discount_summary`, `has_bundles`, `has_subscriptions`.
- **Failure modes:**
  - The homepage is never passed to `extract_products` (it is skipped in the loop), so featured
    products on the homepage do not count.
  - Card price = first number in the text of the first selector in a fixed list (`sale-price`,
    `regular-price`, ..., `.price`, ...; product_extractor.py:544) whose text contains `$`; on
    Dawn and WooCommerce cards that is the whole `.price` block, so the first number wins.
    Compare-at = first match of a second list in which `.price-item--regular` comes before
    `s`/`del` (:588). On Dawn cards both resolve to the current price, on WooCommerce cards both
    resolve to the struck-through price, so neither store is ever "on sale".
  - JSON-LD product prices never carry a compare-at price; JSON-LD `@graph` is not searched in the
    Shopify path.
  - Shopify JSON: integer prices > 100 are divided by 100 (cents heuristic); compare-at is only
    read when numeric, so string `compare_at_price` values from `/products.json` are dropped while
    `is_on_sale` is still computed by string comparison.
  - If no product has a price, the homepage HTML is scanned by seven methods in fixed precedence
    and the first non-empty one wins (`price_extractor.py:36`).
  - The page loop stops at `max_products`.

### policies
- **Owner:** per-page `extract_policies()` modules/policy_extractor.py:329 (only for pages whose
  type is `policy` or whose URL contains `shipping`/`return`), evidence level assignment
  main.py:713-760, shipping fallback main.py:828-858, `extract_policies_from_homepage_js()`
  modules/policy_extractor.py:372.
- **Input:** fetched policy-like pages, homepage promo threshold, homepage HTML.
- **Output:** `shipping_policy` (threshold, regions, days) and `return_policy` (days, free returns,
  conditions), each with an evidence level 1/2/3.
- **Failure modes:**
  - A later page only replaces an earlier policy when it has a threshold / return days.
  - When no shipping policy page parsed, an ad-hoc object is built with `regions=['United States']`.
  - The homepage-JS fallback sets `free_shipping_threshold = 0` (= "free on all orders") whenever
    the raw HTML contains both "free shipping" and "free returns" and no "over $N" phrase.
  - Evidence level 4 ("blocked by robots.txt") and `policy_evidence.py` are never used.

### ai (optional)
- **Owner:** `AIAnalyzer.analyze_site()` modules/ai_analyzer.py:733 called from main.py:1145-1170.
- **Input:** `intel.to_dict()`.
- **Output:** `ai_insights` (Ollama chat, parsed by `##` headings), `ai_positioning` (Ollama),
  `ai_pricing` (XGBRegressor/RandomForest fit at start-up on 500 synthetic rows),
  `ai_threat` (weighted rubric `ThreatScorer`, no model).
- **Runs only** with `--ai` **and** a reachable Ollama with the model pulled; otherwise skipped
  for every site with one console warning.
- **Failure modes:** reads `free_shipping_threshold`, `return_days`, `free_returns` as top-level keys
  that `to_dict()` never produces (they are nested in `shipping_policy` / `return_policy`), so the
  prompt always says N/A for them and the threat rubric's shipping factor is always neutral;
  `ollama_host` in `AIConfig` is never passed to the client; LLM failures fall back to template
  text that is still shown under "Key Insights (AI Analysis)".

### snapshot
- **Owner:** `SnapshotStore.save_snapshot()` modules/snapshot_store.py:77.
- **Input:** `SiteIntelligence`. **Output:** a row in `snapshots` (SQLite at `db_path`), keyed by
  `domain`.
- **Failure modes:** sites that failed to load are stored too; `domain` comes from
  `extract_domain()`, which drops the port and returns the bare IP/host for addresses without a
  public suffix, so `http://127.0.0.1:8001` and `http://127.0.0.1:8002` share history.

### change_diff (--monitor only)
- **Owner:** `SnapshotStore.compute_changes()` modules/snapshot_store.py:191, called at main.py:1128.
- **Input:** current `SiteIntelligence`; stored history.
- **Output:** `ChangeReport` or `None`.
- **Failure modes:** it runs **before** the current scan is saved but reads the second-newest row
  (`LIMIT 1 OFFSET 1`, :155). On the second scan it finds nothing (a real change is missed); from
  the third scan on it reports the difference between the previous two scans, one scan late.
  Change text is Chinese regardless of `--lang`.

### report
- **Owner:** `ReportWriter.write_full_report()` modules/report_writer.py:144 (report.md :177,
  report.csv :612); `BusinessReportGenerator.generate_report()` modules/business_report.py:42;
  rule-based text from `InsightGenerator` modules/insight_generator.py:20.
- **Input:** every `SiteIntelligence` produced (including failed sites), change reports, scan
  history from SQLite.
- **Output:** `report.md`, `report.csv` (UTF-8 BOM), `business_report.md`.
- **Failure modes:**
  - `InsightGenerator` stores `language` and never uses it: key insights, recommendations, evidence
    and change lines are Chinese under `--lang en`.
  - business_report.md prints fixed sentences regardless of the data ("Multiple players in similar
    price ranges", "Heavy reliance on Shopify ecosystem", "AI-powered insight generation using
    Qwen2.5 LLM", "respecting robots.txt"), even for one site, without `--ai`, with
    `--ignore-robots`.
  - "Free shipping" counts only a threshold of exactly 0; a $50 threshold is "no free shipping".
  - A failure in business_report generation is logged as a warning and the run still succeeds.
