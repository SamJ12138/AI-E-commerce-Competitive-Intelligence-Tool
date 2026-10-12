# Phase 3 changes

One section per batch, in commit order. Branch `restructure`, not pushed. Each batch: RED test
first, then the fix, full suite through the pre-commit hook.

## Batch 1 - never synthesize a page the server did not return

- `HttpClient.PROTECTED_SITES` (lululemon.com, shop.lululemon.com, nike.com, adidas.com) and
  `_fetch_protected_site()` are deleted. That method returned made-up HTML with status 200 and a
  `X-Bot-Protection: detected` header when the `--render-js` chain failed for one of those domains.
  It was generated content, not a bypass, so owner decision A3 does not cover it.
- Those domains now go through the same chain as every other site (default `requests -(403)->
  cloudscraper`; `--render-js` `browser -(403/error)-> cloudscraper`) and end as `blocked` or `ok`
  on what the server actually answered. The fetch chain is otherwise unchanged (A3).
- Deleted with it: main.py's check for the placeholder text ("Bot protection detected"), the
  `protected_site` field of the obs `fetch` event, the `placeholder` branch label in reports, and
  the Phase 2 test that fed a fake placeholder page to `analyze_site`.
- `tests/test_fetch_provenance.py`:
  - every combination of outcomes (200 / 403 / 403 with a challenge body / 404 / no response) for
    the first branch and cloudscraper, for both chains, on the formerly protected hosts and an
    ordinary one: the body `fetch()` returns is `None` or exactly a body a stubbed transport
    returned, and the status is the status of the last branch tried;
  - `https://www.nike.com` with browser 403 and cloudscraper 403 ends `status=blocked`,
    `fetch_attempts = [browser 403, cloudscraper 403]`, every field unknown;
  - no string constant in `main.py` or `modules/*.py` contains `<html`, `<!doctype` or `<body`.
  RED before the change: 4 of 5 failed (the default-chain matrix passed; the placeholder was only
  on the `--render-js` chain).

Fixture scores unchanged (all four runs 16/0/0).

## Batch 2 - robots 5xx, products.json, single homepage fetch, Woo announcement

- **robots.txt (RFC 9309 2.3.1).** 2xx: rules apply. 4xx ("unavailable"): no rules, every URL
  allowed (unchanged). 5xx, a timeout or no answer ("unreachable"): every URL of that host is
  disallowed for the run; before, all three meant "allowed". `RobotsChecker.unreachable_reason()`
  says why, and main.py prints it when it skips the site ("robots.txt answered HTTP 503: RFC 9309
  says disallow all"). More than five redirects is treated as unavailable (allowed), as 2.3.1.2
  permits. The robots timeout is `min(10, config.timeout)` (was a fixed 10 s). Still fetched once
  per host per run. Tests (`tests/test_robots_rfc9309.py`, a local server per status): 200, 404,
  403, 500, 503, timeout, connection refused, one fetch per run, `--ignore-robots`.
- **Shopify `/products.json`** is requested only when the homepage has an attribute pointing at a
  same-host JSON product endpoint: `/products.json`, `/collections/<c>/products.json`,
  `/products/<handle>.json|.js|.oembed` (`main.products_json_linked`). Links to product *pages*
  (`/products/<handle>`) do not count: the shopify_basic fixture links its product pages and does
  not serve `/products.json`, which was the last 404. Otherwise an obs `skip` records why.
- **One homepage fetch.** `HttpClient.last_headers` keeps the headers of the last fetch;
  analyze_site reads them right after the homepage fetch and passes them to platform detection.
  The second `client.fetch(url)` is gone.
- **WooCommerce announcement.** The header fallback in `_extract_announcement_bar` took the first
  child of `<header>` when its text contained a promo word as a substring; on Storefront that is
  the wrapper holding the logo and the menu ("Shipping" contains "ship"). A first child that holds
  a `nav` / list or more than one link is now skipped. `.woocommerce-store-notice` (the WooCommerce
  store notice) is the first announcement selector, and selector text is read without dismiss /
  close controls (no trailing "Dismiss").
- **Ground truth:** `announcement_bar` added to all three fixtures.json (`Free shipping on orders
  over $50`; `Summer Sale: 20% off everything, applied automatically. Free shipping on orders over
  $75.`; null for blocked) and to score_fixtures.py, so runs are scored on 17 fields.

RED before the change (sources stashed): 25 new tests, 22 failed; the robots 200, 404 and 403 cases
already passed.

| run | requests before | 404 before | wall before | requests after | 404 after | wall after |
|---|---|---|---|---|---|---|
| shopify_basic | 9 | 1 (products.json) | 11.4 s | 7 | 0 | 8.5 s |
| woocommerce_promo | 8 | 0 | 10.1 s | 7 | 0 | 8.5 s |
| blocked | 3 | 0 | 1.1 s | 3 | 0 | 1.0 s |
| blocked_render_js | 5 | 0 | 5.0 s | 5 | 0 | 4.9 s |

Fixture scores: 17/0/0 on all four runs (announcement_bar was a mismatch on woocommerce_promo
before the fix).
