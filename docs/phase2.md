# Phase 2 changes

One section per batch, in commit order. Fixture scores are re-measured after every batch with
`python scripts/score_fixtures.py`; Phase 1 numbers are in `docs/baseline/`.

## Batch 1 - B1: synthetic ML removed, rule-based pressure score

- `PricingPredictor` (XGBoost / RandomForest fitted at start-up on 500 `np.random` rows) is deleted
  with its report section ("Pricing Strategy Recommendations": competitor median, suggested
  low / optimal / high), its translation keys, its config keys (`enable_pricing_prediction`,
  `pricing_model_path`) and the `data/*.pkl` ignore rule.
- `ThreatScorer` ("ML classification", no model) becomes `modules/pressure_score.py`:
  **competitive pressure score (rule-based)**. Same six factors and weights, same 1-10 rounding.
  report.md prints, per site, the score, the exact weighted sum, and a table of every factor with
  its weight, factor score, weighted contribution, inputs and rule. The unused
  `GradientBoostingClassifier` / `LabelEncoder` imports, `enable_threat_scoring` and
  `threat_model_path` are gone.
- Two behaviour changes in the score, both because the old inputs were wrong:
  - it runs on every scan; before it only ran with `--ai` **and** a reachable Ollama, although
    nothing in it uses the LLM;
  - the shipping factor reads `shipping_policy.free_shipping_threshold`; the old code read a
    top-level key `to_dict()` never produces, so that factor was always the neutral 5.
- AI wording: report.md shows the AI banner, "Key Insights (AI)" and the positioning text only
  when the Ollama step produced that text (`SiteIntelligence.ai_model` is set only then, and names
  the model). The template fallback (`建议启用Ollama...`) is never shown as AI output. The business
  report's methodology names the LLM and model only for the sites where it ran; otherwise it says
  the analysis is rule-based.
- requirements.txt: removed xgboost, scikit-learn, numpy, html5lib, pandas, sqlite-utils,
  python-dateutil, html2text, ratelimit, deepdiff. Batch 6 does not need deepdiff (change detection
  is a field-by-field comparison in `snapshot_store.py`), so its unused import is removed too.
  `tests/test_dependencies.py` fails if a requirement is not imported or a removed one comes back.
- Not exercised here: no Ollama in this environment. The analyzer contract is tested with a stubbed
  `OllamaClient` (`tests/test_ai_labels.py`).
- Fixture scores unchanged (shopify 12/1/3, woo 9/1/6, blocked 10/0/6).

## Batch 2 - fetch the pages that matter

- Discovery now starts from the links on the homepage that `analyze_site` already fetched (no
  third homepage request). Collection, product and policy links are kept, query strings dropped,
  robots.txt checked per URL; cart / checkout / account / add-to-cart links are never followed.
- Guessed paths are platform-known only and only for the page kinds the crawl did not find:
  Shopify `/collections/all`, `/policies/shipping-policy`, `/policies/refund-policy`;
  WooCommerce `/shop`, `/refund_returns`. Nothing is guessed for other platforms. The 22-path
  `get_priority_pages()` list is deleted, and so is main.py's unconditional `/collections/all`
  insertion.
- Sitemaps are read only when no product page was found: those declared in robots.txt, else the
  platform's own location (Shopify `/sitemap.xml`, WordPress `/wp-sitemap.xml`).
  `RobotsChecker.get_sitemaps()` no longer guesses `/sitemap.xml` and `/sitemap_index.xml`.
- `categorize_page_type()` recognises `/shop`, `/collections`, `/catalog`, `/categories` without a
  trailing segment and `/product-category/...`.
- Inside `max_pages` (the homepage counts as one) pages are ordered collections, shipping/returns
  policies, products, other policies, so a long product list cannot push the policies out.
- Shopify `/products.json` is still requested (a platform API, not a page guess); it is the one 404
  left on the fixture.

| store | requests | 404s | wall time |
|---|---|---|---|
| shopify_basic before | 26 | 20 (16 guessed paths, 3 guessed sitemaps, products.json) | 38.0 s |
| shopify_basic after | 9 | 1 (products.json) | 11.5 s |
| woocommerce_promo before | 25 | 21 (18 guessed paths, 3 guessed sitemaps) | 36.6 s |
| woocommerce_promo after | 8 | 0 | 10.0 s |

Every page listed in each store's fixtures.json is now fetched (before: no product page on either
store, neither WooCommerce policy page). woocommerce_promo `free_returns` now matches (False, from
`/refund_returns`); its `return_days` is still null because no return-days pattern matches "lasts
14 days" (fixed in Batch 3). Still one redundant request per site: the homepage is fetched a second
time only to read response headers for platform detection (`main.py`, platform stage).

## Batch 3 - extraction fixes

- **Prices.** In a card or on a product page the struck-through amount (`<s>`, `<del>`, compare-at
  elements) is read as the compare-at price and removed, together with screen-reader-only text,
  before the current price is read (Dawn `.price-item--sale`, WooCommerce `<ins>`). A product page
  yields its own product (h1 title, page URL, nearest price block) instead of every card-like block
  on it. Products are de-duplicated by URL path, so `/product/x/` (card link) and `/product/x`
  (page) are one product; before, woocommerce_promo counted each product twice. Shopify product
  JSON: strings are dollars (`/products.json`), integers are cents (theme JSON), compare-at is read
  in both forms. `has_discounts` is true when any compare-at price exceeds its price.
- **Loyalty.** Whole-word loyalty wording ("loyalty", "rewards program", "earn N points", ...) or a
  loyalty app's own signature (Smile.io, LoyaltyLion, Yotpo Loyalty/Swell, Stamped loyalty, ...).
  A review widget (Yotpo reviews, Judge.me) is not a loyalty program, and neither are "member",
  "points" or "vip" on their own.
- **Google Analytics.** Only from `<script>` elements: a gtag.js / analytics.js loader `src`, a
  `gtag('config', ID)` or `ga('create', ID)` call. IDs are matched case-sensitively
  (`G-XXXXXXX`, `UA-NNNN-N`); class names (`header__heading-link`) and page text never count.
- **Payment methods.** Card brands are reported by name (Visa, Mastercard, American Express;
  Discover only from payment icons because the word is common copy). "Credit Card" appears only
  when cards are mentioned and no brand is named. Every method is matched as a whole word
  ("affirmation" is not Affirm).
- **Brand positioning.** `generate_brand_description_zh()` (keyword lookup over the first 5000
  characters of HTML) is deleted. Positioning is the page's meta description, else the tagline part
  of `<title>`, else a hero headline of three or more words, quoted verbatim with its source; else
  null. Field renamed `brand_description_zh` -> `brand_positioning` (+ `brand_positioning_source`),
  also in the snapshot JSON.
- **Language.** `InsightGenerator` now has English and Chinese templates (it ignored `language`
  before); change sentences are produced in the report language (`compute_changes(language=...)`);
  the remaining English lines in the Chinese business report and the Chinese footer in the
  English report.md are translated. `tests/test_language.py` writes all three reports for both
  stores plus a change report in each language: no CJK character under `--lang en`; under
  `--lang zh` no English word except site data (names, URLs, quoted page text) and product names
  / acronyms (Shopify, WordPress, PayPal, SWOT, ...).
- **Return window** (not in the brief's list, needed for the Batch 7 gate): "our refund and returns
  policy lasts 14 days" and "within N days of purchase" are recognised.

Not changed: report.csv keeps English column names under `--lang zh` (it is a data schema);
quoted page text stays in the page's own language under either `--lang`. Seen but not fixed
(no fixture field scores it): woocommerce_promo's announcement bar is the header nav text
("Harbor Supply Co.HomeShop...").

Fixture scores: shopify_basic 12/1/3 -> 16/0/0, woocommerce_promo 10/1/5 -> 16/0/0.

## Batch 4 - a blocked site is unknown, not False

- `SiteIntelligence.status`: `ok`, `blocked` (some fetch branch got an HTTP answer, none was
  usable) or `unreachable` (no HTTP answer at all; not in the brief, added so a DNS or connection
  failure is not reported as "blocked automated access"). `fetch_attempts` lists the branches
  tried, e.g. `requests 403`, `cloudscraper 403`. For any status but `ok`, `mark_unknown()` sets
  every extracted field to None (lists empty): no platform, no currency, no booleans.
- The branch list comes from `HttpClient.last_chain`, set where each fetch is already logged.
  The fetch chain itself is unchanged (owner decision A3).
- The `PROTECTED_SITES` placeholder (synthetic HTML that `HttpClient` returns with status 200 for
  lululemon/nike/adidas after the browser and cloudscraper fail) is now reported as `blocked`
  (`browser 403 -> cloudscraper 403 -> placeholder 200`) instead of being analysed as if it were
  the site. The placeholder is still produced; only its text is no longer read as data.
- report.csv has `status` and `fetch_attempts` columns; a blocked row has empty cells.
- report.md and business_report.md state "blocked automated access" (or "could not be reached")
  with the branches tried, and leave the site out of the comparison table, the pressure score,
  insights, averages, percentages, SWOT and recommendations. "Competitors Analyzed" counts only
  analysed sites. With no analysed site the business report says so and has no findings.
- No change report is computed from or against a blocked scan; the AI step skips blocked sites.

Fixture scores: blocked 10/0/6 -> 16/0/0 and blocked_render_js 10/0/6 -> 16/0/0 (status=blocked,
every field null); shopify_basic and woocommerce_promo stay 16/0/0.

## Batch 5 - business report says only what the data supports

- `business_report.py` is rewritten around the number of analysed (non-blocked) sites `n`:
  - `n = 0`: no findings, no comparison, no recommendations; blocked sites are listed.
  - `n = 1`: findings describe that site (platform, price range and median, how many of its
    products are marked down, shipping offer, return window, loyalty). No market overview,
    comparison table, averages, percentages, "competitor" or "multiple players".
  - `n >= 2`: counts are "k of n sites"; averages are named for what they are (the average of the
    sites' median prices); the comparison notes are computed (all on one platform, price ranges
    overlap or not, all/none offer free shipping) instead of the fixed "Heavy reliance on Shopify
    ecosystem" and "Multiple players in similar price ranges" sentences.
  - Free shipping counts any threshold; before, only a threshold of exactly 0 counted, so a store
    with free shipping over $50 was "no free shipping".
  - Recommendations are built from the data (this site's / the sites' price ranges, thresholds,
    return windows, loyalty) instead of fixed 0-3 / 3-6 / 6-12 month boilerplate.
  - "Competitors Analyzed" became "Sites Analyzed".
- Methodology states what ran: pages fetched per site and the fetch branch that served them
  (`HttpClient.served_counts`, recorded where fetches are already logged), whether robots.txt was
  respected or ignored, whether JavaScript rendering was used, and whether the LLM step ran (model
  named), was requested but Ollama was unavailable, or was not requested. main.py passes these in
  `run_info`. The evidence-level table lists levels 1-3; level 4 ("blocked by robots.txt") is never
  produced and is no longer listed.
- AI prompt (`ChineseInsightGenerator._build_prompt`): only fields `to_dict()` produces; shipping
  and return values read from the nested policies (they were read from top-level keys that never
  exist, so the prompt always said N/A); a line is omitted when its value is unknown; the threat
  and pricing sections (parsed into fields nothing printed) are no longer requested. The
  positioning prompt omits unknown values instead of printing "$0 - $0".
