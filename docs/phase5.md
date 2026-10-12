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
