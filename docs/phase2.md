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
