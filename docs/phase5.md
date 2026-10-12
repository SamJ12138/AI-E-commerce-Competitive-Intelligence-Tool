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

### beardbrand, brooklinen: return-window and free-shipping phrasing

- Return window: "can be returned or exchanged within 365 days" (brooklinen), "full refunds ...
  (usually up to 120 days from the date of purchase)" and "Full refund up to 120 days from order"
  (beardbrand). "within N days of purchase / from delivery" now counts only in a sentence about a
  return, refund or exchange: "Orders ship within 3 days of purchase" used to be read as a 3-day
  return window.
- Free-shipping threshold: "Luxury shipping is free for US domestic orders over $100" and "Free
  luxury shipping on US orders $100+" (beardbrand).
- RED: `tests/test_policy_phrasing.py` 8 of 11 failed (three are unchanged controls). On the saved
  pages: brooklinen's returns page 365 days, beardbrand's returns page 120 days and FAQ $100; the
  other stores' pages give the same values as before.

### brooklinen: a link to the rewards page is a loyalty program

- brooklinen links `/pages/rewards` from its account menu (an icon) and its footer ("Brooklinen
  Rewards"); the homepage has no other loyalty wording and the rewards page itself is not crawled
  (category `other`). A link whose path has a `rewards` / `loyalty` segment (`/pages/rewards`,
  `/pages/ritual-rewards`, `/account/loyalty`) now counts; product, collection, shop and blog paths
  do not (brooklinen's homepage also links products named `rewards-...`).
- RED: `tests/test_loyalty_link.py` 4 of 8 failed (the four non-program links are controls). On the
  saved homepages only brooklinen changes (False -> True).

### barefootbuttons: account forms and menu entries are not email capture

- barefootbuttons' only email fields are WooCommerce's login and register forms (`#reg_email`
  matched `input[name*="email"]`), and its header "Newsletter" menu item links to
  `#header-newsletter-signup`, which is not on the page (`span.header-newsletter-title` matched
  `[class*="newsletter"]`). Fields in forms whose id, action or class names login, register,
  account, password, checkout, search or cart no longer count, and neither does an element with no
  field of its own that is, or sits in, a link, a button, a nav or the header. A footer newsletter
  block without a field (Klaviyo draws the form, deathwishcoffee) still counts.
- RED: `tests/test_email_capture.py` 4 of 8 failed, then 2 more once the fixture had barefootbuttons'
  span inside the menu link (the first fix only skipped the `li` itself and the saved homepage still
  matched the span). On the saved homepages only barefootbuttons changes (True -> False).

### porterandyork: email capture unknown when only a form script is loaded

- porterandyork's HTML has no email field or sign-up text, but Klaviyo's onsite script is loaded and
  can draw a sign-up form in the browser; the ground truth is "undeterminable from the HTML" and the
  tool said False. When no sign-up is found and a form script is loaded (Klaviyo onsite, Privy,
  Omnisend, Mailchimp's popup script, Justuno, OptinMonster), `has_email_capture` is now None
  (unknown): an empty CSV cell, "unknown" in the pressure-score inputs, absent from the tactic
  lists. With `--render-js` the drawn form is in the page and gives a definite answer.
- RED: 2 new cases in `tests/test_email_capture.py` failed (False instead of None; the report
  case); two controls passed. On the saved homepages only porterandyork changes (False -> None).

### brooklinen: the first real --render-js run

One run, 2026-10-12, `--render-js` with otherwise default settings, cloudscraper off (the
`real_corpus.py run` setup plus `--render-js`; a hook saved each rendered page to the session's
scratch directory, not to the repository). It was brooklinen's one visit in this batch, made after
the static-HTML fixes above.

- Fetch branches: the browser (Chrome via Playwright; patchright is not installed) served all 12
  pages, status 200 each: homepage, 9 collections, FAQ, returns page, shipping policy, one product
  page. robots.txt went through `requests` as always. No page fell back to `browser->requests`.
- Wall time 69.4 s for 12 pages (homepage 9.4 s, then about 4.2-4.8 s per page: the fixed 3 s wait
  plus load). The Phase 3 default-settings run took 20.9 s for 14 pages.
- Products: 50 sampled from 7 collections and 1 product page (the default run found none: the
  catalogue is drawn by JavaScript). Every other field matched the ground truth in this run
  (threshold 100, 365 days, free returns False, payment methods, Yotpo, loyalty True, email True).

What the browser path got wrong:

- **Card titles were badges.** On the rendered cards the image link, which carries a text badge
  ("Best Seller", "Cooling", "New to Sale"), comes before the title link; with no title selector
  matching, the first product link's text was the title (21 of the 32 products of the replay).
  Badge and eyebrow elements are now left out of link text.
- **The struck-through price was not read.** Rendered cards show "From: $199 $169 15% off" with the
  $199 in `span.Price__Default.--slashout`; only `<s>`/`<del>`/compare classes counted, so the
  current price was right and compare-at was None (no discount seen). `[class*="slashout"]`,
  `[class*="strikethrough"]` and `[class*="compare-at"]` are compare-at markers now.
- **An HTTP error in the browser was content** (found reading the browser branch for this run, not
  hit in it: every page was 200). `_fetch_with_playwright` returned the body of a 403 / 404 / 429 /
  5xx page with no error, so without the cloudscraper fallback (real-site runs switch it off) a
  challenge page would be parsed as the store. It now returns an error like the requests branches.
- RED: `tests/test_rendered_cards.py` 2 of 3 failed (badge titles, compare-at; one control);
  `tests/test_browser_status.py` 4 of 5 failed (403, 404, 429, 503 returned as content; one
  control). Replaying the saved rendered pages on 127.0.0.1 (no network): badge titles 21 -> 0,
  Dreamweave Waffle Robe 118 with compare-at 139, Throw Blanket 110 / 129, Down Comforter 169 / 199,
  has_discounts False -> True.

Not fixed, filed:

- **The ground truth and the rendered page disagree on brooklinen's prices.** The ground truth was
  read this morning from the static HTML and product JSON: Down Comforter $199, Robe and Throw from
  $129, no compare-at price. The rendered cards in this run show every one of them 15% off ($169,
  $118, $110 with the regular price struck through), a discount that is applied in the browser and
  is not in the product JSON. The ground truth is not changed after reading the tool's output, so
  the three products score as mismatches; which one a report should state is for the owner.
- Down Pillow is in none of the 7 sampled collections (its collection, duvet-inserts-pillows, is
  beyond `max_pages`).
- Under `--render-js`, `products.json` and sitemap XML would also be loaded in the browser, which
  wraps them in HTML, so they would fail to parse. Not hit in this run (the homepage links product
  pages, so no sitemap was read, and it links no JSON endpoint).

### Reruns (one per store) and scores

allbirds, barefootbuttons, beardbrand, deathwishcoffee, porterandyork and rastaclat were run once
each after the fixes above (default settings, cloudscraper off); brooklinen's one run is the
`--render-js` run above; louboutin (blocked) was not rerun.

| store | Batch 1 table | after Batch 2 | pages |
|---|---|---|---|
| allbirds | 7/1/2/0 | 10/0/0/0 | 13 |
| barefootbuttons | 8/0/2/0 | 9/1/0/0 | 9 |
| beardbrand | 5/1/2/2 | 8/1/1/0 | 20 |
| brooklinen | 7/0/1/2 | 9/0/1/0 (`--render-js`) | 12 |
| deathwishcoffee | 9/0/1/0 | 10/0/0/0 | 17 |
| louboutin | 10/0/0/0 | 10/0/0/0 (not rerun) | 1 |
| porterandyork | 9/0/1/0 | 9/0/0/1 | 20 |
| rastaclat | 9/1/0/0 | 9/1/0/0 | 13 |
| **total** | **64/3/9/4** | **74/3/2/1** | |

(match/partial/mismatch/missing.) Per field: threshold 8/8, return window 8/8, email capture 8/8,
free returns 7 + 1 missing, loyalty 7 + 1 mismatch, payment methods 7 + 1 partial, products
5 + 2 partial + 1 mismatch. What is left, and the two disagreements with the ground truth
(brooklinen's rendered discount, rastaclat's Klarna), are in `docs/observations.md` section 11.

- rastaclat: Google Pay is now found (product pages are reached since Batch 1), and Klarna, which
  the ground truth does not list, comes with it.
- barefootbuttons: products 4 -> 3 of 4, a Batch 1 effect: one collection, so 10 products
  instead of 50.
- porterandyork: free returns match -> missing; the returns page timed out in this run.

## Batch 3 - the --ai step

- `ollama --version`: command not found. Ollama is not installed on this machine (the `ollama`
  Python package is, in the venv), so there is no sample from a real model and no
  `docs/sample/ai/`. The README says the step is implemented but not verified with a real model.
- `tests/test_ai_fake_ollama.py` runs `main.py --ai --ai-model fake-model:1` on the Shopify-style and
  the blocked fixture stores with a stand-in `ollama` module (its `list()` offers the model, its
  `chat()` records each call and answers). It checks: two calls, both for the store that was read
  and none for the blocked one; every fact line of the insight prompt has a known label and the
  value the pipeline reported in `report.csv` (domain, platform, price range, threshold, return
  window, free returns, review platform, payment methods, email capture), and a value the pipeline
  did not produce (review count) is left out, with no "N/A" or "None"; the positioning prompt quotes
  the page's own description; `report.md` prints the insights, the recommendation and the
  positioning text under "Key Insights (AI)", "Actionable Recommendations (AI)" and "Brand
  Positioning Analysis (AI)" in that store's section, with the model named, and nothing from the
  model in the blocked store's section; `business_report.md` names the model.
- The code under test already existed, so there was no failing test to fix. To check the test can
  fail, two mutations were run and reverted: a made-up fact line in the prompt
  (`威胁等级: 高`) failed the prompt test; printing the insights under the recommendations heading
  failed the report test. 5 tests, about 2 s.
