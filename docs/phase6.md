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
