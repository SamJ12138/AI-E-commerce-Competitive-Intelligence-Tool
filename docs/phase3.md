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

## Batch 3 - a real-store corpus and baseline scores

Eight stores, ground truth read by hand on 2026-10-12 (`docs/real-corpus/README.md` has the method;
one `<store>.json` per store with the URL every fact came from; no page HTML is committed):
rastaclat, pfrankmd, allbirds (sites.txt); deathwishcoffee (coffee) and brooklinen (bedding) as the
other two Shopify stores; porterandyork and barefootbuttons (WooCommerce); Christian Louboutin US
(Magento) as the store expected to block. 55 page GETs (3 of them 404 on barefootbuttons) plus one
robots.txt per host, all with `requests`, one GET per URL, robots.txt
respected; allbirds disallows `/policies/`, so its shipping policy was not read.

`scripts/real_corpus.py run` ran main.py once per store with default settings, except that the
cloudscraper fallback was switched off in the launching process (real-site runs never take the
cloudscraper path). `score` wrote `docs/real-corpus/scores.md`. Nothing was fixed in this batch.

| store | status | match | partial | mismatch | missing |
|---|---|---|---|---|---|
| allbirds | ok | 2 | 0 | 1 | 7 |
| barefootbuttons | blocked (requests 403) | 3 | 0 | 1 | 6 |
| brooklinen | ok | 1 | 0 | 2 | 7 |
| deathwishcoffee | ok | 2 | 0 | 2 | 6 |
| louboutin | blocked (requests 403) | 10 | 0 | 0 | 0 |
| pfrankmd | ok | 10 | 0 | 0 | 0 |
| porterandyork | ok | 6 | 0 | 1 | 3 |
| rastaclat | ok | 2 | 0 | 1 | 7 |

What the baseline shows (10 fields per store: status plus the 9 ground-truth fields):

- **Six of eight stores were read as garbage.** Every store behind Cloudflare that answered 200
  (allbirds, brooklinen, deathwishcoffee, pfrankmd, porterandyork, rastaclat) produced
  `platform = Custom/Unknown`, no products and no policies, although the homepage answered 200. The
  tool's session sends `Accept-Encoding: gzip, deflate, br` (`HttpClient._create_session`, part of
  the browser header set) and the venv has no Brotli decoder (`brotli` / `brotlicffi` not installed),
  so urllib3 hands back the Brotli bytes undecoded and they are parsed as HTML. The ground-truth
  fetches (plain `requests`, which only advertises encodings it can decode) received the real pages:

  | store | tool: status | server | tool: body (decoded as text) | ground truth: status | ground truth: bytes |
  |---|---|---|---|---|---|
  | allbirds | 200 | cloudflare | 170,830 | 200 | 714,523 |
  | brooklinen | 200 | cloudflare | 240,343 | 200 | 1,904,448 |
  | deathwishcoffee | 200 | cloudflare | 118,354 | 200 | 642,751 |
  | pfrankmd | 200 | cloudflare | 17,077 | 200 | 50,363 |
  | porterandyork | 200 | cloudflare | 60,652 | 200 | 196,845 |
  | rastaclat | 200 | cloudflare | 141,694 | 200 | 401,110 |

  The 4-8x size ratio is a compression ratio. Downstream this shows up as `missing` almost
  everywhere and as definite `False` for `has_email_capture` / `has_loyalty` (5 stores): a page the
  tool could not read is reported as having no email capture and no loyalty program. pfrankmd's
  10/10 and porterandyork's matches on "no free shipping" / "no return window" are accidental: nothing
  was read, and nothing is what those pages state.
- **porterandyork** still fetched 24 pages: its sitemaps (`/sitemap_index.xml` and children) were
  readable and listed product URLs, but every HTML page was Brotli as well.
- **barefootbuttons blocked the tool, not the ground-truth reader.** nginx answered 403 to the tool's
  Chrome User-Agent and browser header set; the same homepage answered 200 to the honest
  `ECI-RealCorpus` User-Agent. With cloudscraper off, the run ends `blocked`, `requests 403`.
- **louboutin** answered 403 (`cf-mitigated: challenge`) to both. The tool ends `blocked`,
  `requests 403`, every field null: 10/10. Its robots.txt sets `Crawl-delay: 60`, which the tool
  does not read (one homepage request, so it did not matter here).
- **pfrankmd is not a store any more** (a dermatology clinic site); kept because it is in sites.txt.

## Batch 4 - fix what the corpus found

Each fix: RED on a hand-written fixture that reproduces the real page's structure, GREEN, full suite,
then one rerun of the 8 stores (`scripts/real_corpus.py run`, same settings as Batch 3).

### Fix 1 - Brotli (6 stores: allbirds, brooklinen, deathwishcoffee, pfrankmd, porterandyork, rastaclat)

- `brotli>=1.1.0` added to requirements.txt (and installed in the venv): urllib3 decodes
  `Content-Encoding: br` only when a Brotli library is importable. The browser header set is
  unchanged (A3): `Accept-Encoding: gzip, deflate, br` is still sent, now with a decoder behind it.
- If no Brotli library is importable, `br` is no longer offered (`Accept-Encoding: gzip, deflate`)
  and an obs `degraded` event says so.
- A response whose `Content-Encoding` this environment cannot decode (`undecodable_encoding()`,
  checked against urllib3's own `ACCEPT_ENCODING`) is a fetch error ("Undecodable Content-Encoding:
  x"), in the requests branch, its SSL retry and the cloudscraper branch: compressed bytes are never
  parsed as a page.
- Fixture: `tests/fixtures/encoded/shopify_home.html` (hand-written Dawn-style homepage) and its
  Brotli copy `shopify_home.html.br` (made once with brotli 1.2.0; a test checks they agree), served
  by a CDN-like local server that answers Brotli when offered, else gzip, else identity
  (`tests/test_content_encoding.py`). RED without brotli in the venv: 4 failed (platform
  `Custom/Unknown`, as on the real stores), 1 skipped.

### Fix 2 - policy pages never fetched on stores with a big menu (allbirds, rastaclat, deathwishcoffee)

After fix 1, return days / free returns / free shipping were still missing on these stores although
their homepages link the returns page. Two causes, the second found only by the rerun:

- The page loop `break`s as soon as `max_products` (50) products are collected
  (`main.py`, "Stop if we have enough products"); on allbirds that is after the first collection.
  Now `max_products` caps products, not pages: once reached, remaining collection / product pages
  are skipped (obs `page_skipped`) and the policy pages are still read. Unique products (by URL
  path) are counted, not raw cards. RED: `analyze_store("shopify_basic", max_products=1)` never
  fetched the two policy pages.
- The rerun with only that change scored exactly the same: the page list itself was 19 collections.
  `_rank()` put every collection first, and a mega-menu links 37 (allbirds) to 56 (deathwish)
  pages, so `max_pages` dropped every policy and product page before the loop
  (`dropped_by_max_pages` in the obs log). `order_pages()` now gives each kind a share: the first
  2 collections, shipping/returns policies, the first 5 products, the remaining collections, the
  remaining products, other policies. RED: a hand-written homepage with 25 menu collections,
  8 products and footer returns / shipping links put no policy page in the list.

Rerun: rastaclat return_days and free_returns, porterandyork free_returns, deathwishcoffee
return_days now match; allbirds fetches `/pages/returns-exchanges` (return_days already matched
from the homepage).
