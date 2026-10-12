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
