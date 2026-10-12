# Real-store corpus

Eight public stores, ground truth written by hand on 2026-10-12. Each `<store>.json` holds facts and
the URL each fact came from, with a short note on what the page says. No page HTML is kept here:
it is the stores' content.

The ground truth for a store is written before the tool's output for that store is read. beardbrand, which replaced pfrankmd.com (a clinic site with no shop), was the
first store added under this rule. Before it, one correction was made after a tool run had been
read: the Shopify payment methods (see `payment_methods.corrected` in those files).

| store | url | platform | category | why it is here |
|---|---|---|---|---|
| rastaclat | https://rastaclat.com/ | Shopify | bracelets | sites.txt |
| beardbrand | https://www.beardbrand.com/ | Shopify | men's grooming | sites.txt (replaced pfrankmd.com, not a store) |
| allbirds | https://www.allbirds.com/ | Shopify | footwear | sites.txt |
| deathwishcoffee | https://www.deathwishcoffee.com/ | Shopify | coffee | Shopify, another category |
| brooklinen | https://www.brooklinen.com/ | Shopify | bedding | Shopify, another category; JS-rendered navigation and prices |
| porterandyork | https://porterandyork.com/ | WooCommerce | meat (perishable) | WooCommerce |
| barefootbuttons | https://barefootbuttons.com/ | WooCommerce | guitar accessories | WooCommerce; refuses browser-like requests |
| louboutin | https://us.christianlouboutin.com/us_en/ | Magento | luxury footwear | expected to block: Cloudflare challenge (403) |

## How the facts were read

- `requests` only, one GET per page (a URL was never fetched twice), 4 s between requests to a
  host, robots.txt fetched once per host and respected (RFC 9309: 4xx = no rules, 5xx or no answer =
  disallow). User-Agent: `ECI-RealCorpus/0.1 (ground truth for an open-source
  competitive-intelligence tool; +https://github.com/SamJ12138/AI-E-commerce-Competitive-Intelligence-Tool)`.
- 5 to 10 pages per store: homepage, one collection / shop page, 4 product pages, the shipping and
  returns pages it links, a rewards page when there is one. `pages_read` in each file lists them.
- Values come from what the page states or declares in its markup (visible text, JSON-LD, product
  JSON, app widgets). `evidence` says which.

## Field conventions

- `null`: the pages read state nothing (no free-shipping offer, return shipping cost not stated, a
  blocked store). A definite answer from the tool is then a mismatch.
- `return_days.accept`: the page states more than one value (deathwishcoffee: "60 day money back
  guarantee" and "within 30 days ... full refund" on the same page); either one is a match.
- `products`: 4 products per store with price and compare-at price. `price_range`: a variable
  product (price differs by size); any price in the range is a match.
- `payment_methods`: brands the pages name or declare. On the four Shopify stores no payment icons
  are shown; the markup declares Shop Pay, Google Pay and cards (`<link rel="buy" payment=...>`),
  PayPal and whether Venmo is on (`in-context-paypal-metadata`, `data-venmo-supported`), and the
  Apple Pay merchant config with its card networks (`apple-pay-shop-capabilities`,
  `supportedNetworks`: Visa, Mastercard, Amex, Discover, JCB, Elo, the same list on all four).
  *Corrected 2026-10-12 after the first Batch 4 rerun:* the first reading took only the
  `<link rel="buy">` and PayPal metadata; re-read from the same saved pages (no new fetch), each
  file's `payment_methods.corrected` says so. The baseline verdicts did not change (the tool
  reported no payment method on those stores).
- `review_platform`: the app whose widget is on the product page; native WooCommerce reviews count
  as none.

## Scoring

```
python scripts/real_corpus.py run --out-root <dir>       # one main.py run per store (real sites)
python scripts/real_corpus.py score --out-root <dir> --md docs/real-corpus/scores.md
```

`scores.md` is the current table; `scores-baseline.md` (before any fix),
`scores-after-batch4.md` (pfrankmd still in the corpus) and `scores-phase4.md` (end of Phase 4) are
kept as history.

`run` uses default settings except that the cloudscraper fallback is switched off (real-site runs
never take the cloudscraper path), so a 403 ends on `requests 403`. `score` writes per store and
per field match / partial / mismatch / missing, and for every miss the obs log's final field event,
the stage and rule that produced the value, and whether the tool fetched the page the fact is on.
