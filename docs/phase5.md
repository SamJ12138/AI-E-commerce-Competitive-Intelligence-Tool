# Phase 5 changes

After the public release. One section per batch, in commit order. Each code change: RED test first,
then the fix, full suite through the pre-commit hook. Real stores: one run per store per batch,
robots.txt and Crawl-delay respected, cloudscraper off.

## Batch 1 - stratified product sampling

- `modules/product_sample.py`: the products a run reports. Each collection page contributes at most
  `max_products_per_collection` products it has not seen yet (config key, `--max-per-collection`,
  default 10); the homepage's priced product cards and Shopify's products.json count as one source
  each, with the same limit; a product page contributes its product. The total stays
  `max_products` (50). Before, the products were the first 50 in crawl order, so one big first
  collection filled the sample and every later collection and product page was skipped.
- Price statistics (min / max / median / discounts) are over the sample. Before, they were over
  every product extracted, which on allbirds was the 194 cards of its first collection while the
  report listed 50.
- The homepage is now read for products. It was already fetched and never used for this.
- `report.md` (data evidence) and `business_report.md` (methodology) state the sample, e.g.
  "50 products from 7 collections (at most 10 per collection), the homepage (10) and 2 product
  pages". The run log has a `product_sample` event with the counts.
- Fixture (`tests/test_product_sampling.py`, pages served by the new `tests/page_server.py`): a
  Shopify-style store with three collections of 60 cards each, priced from $5, $40 and $200.
- RED: 9 of 9 failed. Only `/collections/budget` was fetched and the range was $5-$20; no
  `max_products_per_collection` in Config or CONFIG_KEYS, no `product_sample`, no sample line in
  the reports, the homepage's cards not in the products.
- GREEN: 285 passed (9 new, 2 parametrised over the new module). Fixture scores 17/0/0 on all
  four runs. The demo's reports (docs/sample) gain the sample line; no other change.

### Real stores (one run each, 2026-10-12)

| store | pages | products found (of 4) | right (of 4) | price range | sample |
|---|---|---|---|---|---|
| allbirds before | 4 | 1 | 1 | $14-$160 over 194 products | 50 of the first collection's 194 |
| allbirds after | 13 | 4 | 2 | $14-$145 over 47 priced | 5 collections, 3 product pages |
| deathwishcoffee before | 12 | 3 | 3 | $11.99-$54.99 | 3 collections, 5 product pages |
| deathwishcoffee after | 17 | 4 | 4 | $5.99-$54.99 | 7 collections, the homepage (10), 2 product pages |

- allbirds: payment_methods partial -> match (Google Pay, declared only on product pages, which the
  run now reaches). The two products found without a price come from their product pages: the
  price is in `meta product:price:amount` and a JSON-LD `ProductGroup`, which the product-page
  extractor does not read (observations section 10; Batch 2).
- deathwishcoffee: Call of the Wild Mug ($38) came from the homepage's product cards; its product
  page and the mugs collection are beyond `max_pages`.
- Corpus 62/5/9/4 -> 64/3/9/4 (match/partial/mismatch/missing). The end-of-Phase-4 table is kept
  as `docs/real-corpus/scores-phase4.md`.

## Batch 2 - the remaining real-store misses

Store by store from `docs/observations.md` sections 8 to 10. Each fix: a hand-written minimal
fixture with the page structure the store serves, RED, fix, GREEN. The stores are rerun once at the
end of the batch.

### allbirds: product-page price from structured data

- The product pages draw their price with JavaScript; the static HTML has it in a JSON-LD
  `ProductGroup` (`offers.price`) and in `<meta property="product:price:amount">`. The product-page
  extractor looked only for a visible price block and fell back to `<body>`. When no visible price
  is found it now reads JSON-LD Product / ProductGroup offers (`price`, an AggregateOffer's
  `lowPrice`, else the first variant's offer), then the product meta tag. A visible price still
  wins.
- RED: `tests/test_product_page_price.py` 4 of 6 failed (price None); the other two are controls.
  On the four saved allbirds product pages (scratch copies from the ground-truth reading, no new
  fetch) the extractor now gives 100, 75, 140 and 105, the ground-truth prices.

### allbirds: privacy and terms text is not a loyalty program

- allbirds' homepage holds its privacy policy and terms of service in hidden modals
  (`div#modal-privacy-policy`, `div#modal-terms-of-service`); "participate in promotions or loyalty
  programs" there set has_loyalty, and the same text set has_referral. Promo detection only reads
  the homepage, so the brief's "policy/privacy/terms pages" are, in the code, blocks inside a page:
  loyalty and referral wording is now read without elements whose id or class names privacy,
  terms, cookie, consent or GDPR (never `<html>`, `<body>` or `<main>`). Loyalty-app signatures in
  the raw HTML still count.
- RED: `tests/test_promo_legal_text.py` 3 of 4 failed (loyalty / referral True from a privacy modal,
  terms text and a cookie banner; the fourth is the control). On the seven saved homepages only
  allbirds changes (loyalty and referral True -> False).

### deathwishcoffee, barefootbuttons, allbirds, beardbrand: free returns only when stated

- `free_returns` has three values now: True when a page says returns are free, False when it says
  the customer pays (responsible for return shipping / the label, a return or restocking fee, a
  return-shipping deduction) or that returns are not accepted, None when it says neither or both.
  Before, a page with no free-return wording gave False, so silence read as "not free"
  (deathwishcoffee, barefootbuttons). "Pain-free returns" no longer counts as "free returns".
  `ReturnPolicy.free_returns` defaults to None; the CSV cell is then empty, and the reports print
  "free" only for True, as before.
- Pages are merged: an accepted return policy page that says nothing about return costs keeps the
  value an earlier page stated, and a page that is not accepted (no return window) fills the value
  when the accepted page did not say (beardbrand: the returns page has the window, the FAQ has
  "a complimentary return label").
- The homepage fallback ("free shipping" and "free returns" anywhere in the homepage HTML) applies
  only when no policy page said anything about return costs (allbirds: the returns page says
  "Customers are responsible for return shipping charges", the fallback set True over it).
- RED: `tests/test_free_returns.py` 9 of 17 failed (silence, "pain-free", mixed and
  not-about-returns wording gave False; the page merge and the fallback guard). The five
  paid-wording cases passed before only because silence was already False.
- On the saved policy pages: allbirds, brooklinen, rastaclat and porterandyork False,
  deathwishcoffee None, beardbrand None on the returns page and True on the FAQ: the ground truth
  for all six.
