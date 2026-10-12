# Phase 6 changes

The four items the owner set after Phase 5: the open decisions on barefootbuttons (sample top-up)
and brooklinen (the homepage price fallback), has_popup, and beardbrand's collection cards. One
section per item, in commit order. Each code change: RED test first, then the fix, full suite through
the pre-commit hook. Real stores: one run per store per item, robots.txt and Crawl-delay respected,
cloudscraper off.

## 1. Sampling top-up from collections already read

- Owner decision on Phase 5's open item (1): after the per-collection quota, if the sample is under
  `max_products`, fill it from the collection pages already fetched, in crawl order. No extra
  requests.
- `ProductSample.add` keeps, for each collection page, the products the quota cut; after the last
  page `ProductSample.top_up()` adds them page by page in crawl order (skipping products already
  sampled) until the cap. Only collection pages are topped up from: the homepage cards and
  products.json keep their limit of 10, and product pages give one product each anyway. The run log
  has a `product_sample_top_up` event per page and `topped_up` in `product_sample`.
- The reports say so: "30 products from 1 collection (10 per collection, then 20 more from the
  collections read)" (Chinese: "每个10个，另从已读集合补充20个"). Without a top-up the line is as before.
- Fixture (`tests/test_product_sampling.py`): one collection with 30 products -> 30 sampled in page
  order, the collection requested once; with `max_products=25`, 25. Three collections of 60 now give
  50 (10 + 10 + 10 by quota, then 20 more from the first collection read).
- RED: 5 of 13 failed (10 sampled instead of 30; no `topped_up`; the report line). The Batch 1 tests
  that counted 30 products from three collections of 60 were written for the old rule: they now set
  `max_products` to the quota total (30, 9, 6) so they still test the quota alone; the default case
  is the new crawl-order test.
- GREEN: 365 passed. The demo reports (docs/sample) are unchanged: no fixture store collection has
  more than 10 products.

### barefootbuttons (one run, 2026-10-12)

| | pages | requests | products (of 4) | sample | price range |
|---|---|---|---|---|---|
| Phase 5 Batch 2 | 9 | 10 | 3 (Max Bore topper not sampled) | 10 from `/shop` | $9.95-$9.95 |
| after | 9 | 10, the same URLs | 4 | 10 from `/shop`, then 40 more from it | $7.95-$10.95, median $9.95 |

barefootbuttons scores 10/0/0/0 (was 9/1/0/0).

## 2. No price range from the homepage text

- Owner decision on Phase 5 Batch 4's open question: the homepage dollar-amount fallback is
  removed. It ran when no product had a price and took the range from every amount written in the
  homepage HTML (5 to 10000, the first 20), so free-shipping thresholds and gift-card values became
  prices (brooklinen's default run in Phase 3: $25-$500).
- `product_extractor.homepage_price_fallback` and its two pattern tables are deleted. When no
  product read has a price, `price_min`, `price_max`, `price_median` and `currency` are null
  (empty CSV cells) and `price_note` is `no_priced_product`. The reports print it: report.md's data
  evidence "Price range: not reported (no product read had a price; other amounts on the pages,
  such as free-shipping thresholds or gift cards, are not used as prices)", business_report.md the
  same under Pricing and Price Range, and the Chinese equivalents. The run log has a
  `no_priced_product` event and each price field's final value comes from it.
- Fixture (`tests/test_no_price_fallback.py`): a store whose product pages have no price and whose
  homepage text has "Free shipping on orders over $75", two prices in a paragraph and "Gift cards
  from $25 to $500". The parametrised fallback cases and the "uses the homepage text" store in
  `tests/test_dead_code.py` tested the removed behaviour and are removed.
- RED: 4 of 4 failed (the fixture gave $25-$500 USD, the gift-card amounts; the function still
  existed; no note in the reports; no `price_note`). GREEN: 363 passed (6 removed, 4 new). Demo
  reports unchanged (every fixture store has priced products).

### brooklinen (one run, 2026-10-12, `--render-js`)

Same setup as its Phase 5 run (`real_corpus.py run` plus `--render-js`, cloudscraper off, a hook
saving each rendered page to the session's scratch directory).

| | pages | wall | price range | from |
|---|---|---|---|---|
| Phase 3, default settings | 14 | 20.9 s | $25-$500 | homepage amounts (no product had a price) |
| Phase 5, `--render-js` | 12 | 69.4 s | $15-$320, median $142.50 | 50 product cards |
| after, `--render-js` | 13 | 79.2 s | $30-$331, median $136.50 | 50 product cards (5 collections, 1 product page) |

- The range comes from the sampled products only: `price_min` and `price_max` are "min / max over
  50 priced products" in the run log, and there is no fallback event. has_discounts is now True
  (the Batch 2 slashout fix: compare-at prices are read).
- Score unchanged, 9/0/1/0. The products miss is the open ground-truth disagreement from Phase 5
  (the rendered cards show 15% off; the ground truth, from the static product JSON, has no
  compare-at). Down Pillow is now in the sample ($118, compare-at $139).
- A default (non-rendered) run of brooklinen, where no product has a price, would now report null
  price fields with the note; it was not run (one run per store per item).

## 3. has_popup

- Before: True when any element's class or id contained popup / modal (and a dozen similar
  selectors), or when the HTML contained the substring klaviyo, privy, sumo, ... anywhere. It was
  True on all seven saved real-store homepages: a mega menu's `global-settings-popup` class
  (deathwishcoffee), a quick-buy modal (rastaclat), the cart lightbox (barefootbuttons), the
  added-to-cart modal (allbirds), a disabled theme popup (beardbrand), a `.modal` that happened to be
  brooklinen's exit overlay. Not scored until now.
- Ground truth first. The fixture stores already had `has_popup` in their ground truth (shopify_basic
  false, woocommerce_promo false, blocked null; the scorer has compared it since Phase 1, and the old
  detector matched because neither fixture page has a modal). woocommerce_promo now has a newsletter
  popup (Popup Maker markup, opened after 5 s, an email field) and its ground truth is true; the
  blocked store stays null, as every field of a store that was not seen (it cannot be "without").
  The eight real-corpus files gained `has_popup`, read from the seven homepages saved in the
  ground-truth reading (no new fetch) before any detector change; louboutin is null (blocked).

| store | ground truth | what the homepage has |
|---|---|---|
| allbirds | null | no marketing popup; Attentive tag loaded (SMS sign-up creative drawn in the browser) |
| barefootbuttons | false | cart and login lightboxes, a cookie banner; no popup script |
| beardbrand | null | theme popup and banner present with `"enabled": false`; Klaviyo onsite loaded |
| brooklinen | true | exit-intent overlay `#overlayModal.js-exit-overlay` ("Hold Up! Stop Right There.", "Start Saving Now") |
| deathwishcoffee | null | inline newsletter block only; Klaviyo onsite and Postscript loaded |
| porterandyork | null | no popup markup; Klaviyo onsite loaded |
| rastaclat | null | quick-buy modals, cart drawer, empty free-gift / BOGO app containers; Klaviyo onsite loaded |

- The detector (`PromoExtractor._detect_popup`) is now three-valued. True: an element whose id /
  class names a popup, modal, overlay or lightbox, or a dialog, that has an email / phone field or
  offer wording (sign up, subscribe, n% off, discount, save, offer, code, ...) or is an exit-intent
  overlay, and that is not a functional overlay (cart, search, menu, drawer, login, account,
  quick-view / quick-buy, policy, cookie / consent, country / geo, product, gift, loading, ...) or a
  disabled one, itself or through an ancestor (up to, not including, `<body>`). None: no such element,
  but a popup script is loaded (Klaviyo onsite, Attentive, Postscript, Privy, Omnisend, Justuno,
  OptinMonster, Wisepops, Sleeknote, Wheelio, Sumo; in a script src or an inline loader's URL list).
  False: neither. `has_popup` is `Optional[bool]` like `has_email_capture`: an empty CSV cell,
  "unknown" in the pressure-score inputs, no "Popup" tactic.
- `scripts/real_corpus.py` scores `has_popup` (11 fields per store).
- RED: `tests/test_popup.py` 19 of 26 failed (every functional overlay but three was True, the
  scripts gave True instead of None, the bare word "klaviyo" counted, the fixture and the scorer).
  GREEN, then on the saved homepages 6 of 7: allbirds loads Attentive through Shopify's inline
  `asyncLoad` URL list (`cdn.attn.tv\/allbirds\/dtag.js`), not a script src; a test for that case
  failed against the src-only check, and inline loaders are read now. 7 of 7.
- Demo sample (docs/sample, en and zh) regenerated: the WooCommerce store shows the popup (tactics,
  "Popup" in the summary table, marketing factor 6 -> 8, weighted sum 5.60 -> 6.00, score still 6).

### The seven stores (one run each, 2026-10-12)

Six with default settings, brooklinen with `--render-js` as its scored run (same hook as item 2).

| store | before (old detector) | after | ground truth |
|---|---|---|---|
| allbirds | True | None (Attentive) | null: match |
| barefootbuttons | True | False | false: match |
| beardbrand | True | None (Klaviyo) | null: match |
| brooklinen | True | None (Attentive) | true: missing |
| deathwishcoffee | True | None (Klaviyo) | null: match |
| porterandyork | True | None (Klaviyo) | null: match |
| rastaclat | True | None (Klaviyo) | null: match |

- brooklinen's rendered `<body>` has `class="truemed-enabled swym-loading"`; "loading" is a
  functional word and the ancestor walk included `<body>`, so the exit overlay was ruled out. The walk
  now stops below `<body>` (page-state classes); test
  `test_page_state_classes_on_body_do_not_hide_a_popup` failed first. Replaying this run's saved
  rendered pages on 127.0.0.1 (no new visit): has_popup True. The scored run is kept as it was
  (missing); brooklinen was not visited a second time for this item.
- Every other field gives the same verdict as the runs before, except porterandyork's free_returns
  (missing -> match: its returns page answered this time; it timed out in Phase 5).
- Is it reliable? On the 7 homepages and both fixture pages the detector gives the ground truth
  (brooklinen through the replay). But only two real stores get a definite value; five load a
  popup script and stay unknown without a browser that waits for the popup's trigger. The column is
  kept, with the unknowns stated: the old one said True on all seven, from a cart, menu, quick-buy,
  added-to-cart or disabled element on five, the bare word "klaviyo" on porterandyork, and (by its
  `.modal` selector) the right element only on brooklinen.
