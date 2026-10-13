# AI analysis sample: allbirds.com, DeepSeek

What `--ai` with `ai_provider: deepseek` wrote for one real store, copied unchanged from the
`report.md` that `scripts/ai_from_snapshot.py` built. Nothing was fetched for it: the scan is the
one stored by the demo-video run (allbirds.com, 2026-10-12 20:37 local time, default settings). The
other files in this folder come from an earlier scan the same day (18:32), whose database was not
kept, so a few values differ (for example, that report lists a popup and this scan's value for it
is unknown).

> **The prompt was changed after this run; this sample reflects the earlier prompt.** Two of the
> errors below came from what the prompt left out. It gave only `has_discounts: yes`, and the
> model called a store with 1 of 50 sampled products marked down a discounter. It gave only the
> sample size, and the model took the sample for the catalogue. The prompt now also lists
> `discounted_products` ("1 of 50 sampled" for this scan) and says the products are a sample of up
> to 10 per collection page, not the full catalogue. The model has not been run on the new prompt.

| | |
|---|---|
| provider / model | DeepSeek / `deepseek-flash` (thinking mode off) |
| run | 2026-10-13 16:57 UTC, one call, `--lang en` |
| prompt tokens | 441 (cache hits 0) |
| completion tokens | 470 (finish reason `stop`) |
| latency | 3.36 s |
| cost | $0.00035: 441 x $0.15 + 470 x $0.60 per million tokens, DeepSeek's published off-peak rate for `deepseek-flash` on 2026-10-13 (the peak rate, 01:00-04:00 and 06:00-10:00 UTC on weekdays, is double: $0.0007) |

An earlier call the same afternoon (16:55 UTC) failed. `deepseek-flash` thinks before it answers
unless told not to, and its hidden reasoning counts against `max_tokens`. That call spent all 1500
tokens reasoning and returned no answer: 466 prompt tokens, 1500 completion tokens, 8.4 s, $0.00097
off-peak. The parser rejected it (`finish_reason: length`, logged as `parse`) and the report said
"AI analysis unavailable". Thinking mode is now switched off for DeepSeek calls. Both calls
together cost $0.0013.

## What was sent

Only these values, as `- field: value` lines, with the instructions in `modules/ai_analyzer.py`
(`build_prompt`). No page HTML; fields the scan did not determine (popup, announcement bar, review
count) were left out.

```
- domain: allbirds.com
- platform: Shopify
- brand_name: Allbirds
- brand_positioning: Allbirds: The world’s most comfortable shoes, flats, and clothing made with natural materials like merino wool and eucalyptus. FREE shipping & returns.
- categories: New Arrivals, All, Bestsellers, LEATHER ALTERNATIVES, Men's Shoes, Sneakers, Slip Ons, Sandals
- products_sampled: 50 products from 5 collections
- price_min: $14
- price_max: $145
- price_median: $105
- currency: USD
- has_discounts: yes
- has_email_capture: yes
- has_loyalty: no
- has_referral: no
- free_shipping_threshold: $100
- return_days: 30
- free_returns: no
- review_platform: Yotpo
- payment_methods: American Express, Apple Pay, Discover, Elo, Google Pay, JCB, Mastercard, PayPal, Shop Pay, Visa
```

## What came back

### 🤖 AI analysis (deepseek / deepseek-flash)

*Written by a language model from the scanned values in this report; each point cites the field it rests on as [field: value]. The tool does not check what the model wrote.*

**Positioning**

Allbirds positions itself as a comfort-first, natural-materials brand, promising "the world's most comfortable shoes, flats, and clothing made with natural materials like merino wool and eucalyptus" [brand_positioning: Allbirds: The world’s most comfortable shoes, flats, and clothing made with natural materials like merino wool and eucalyptus. FREE shipping & returns.]. Its pricing spans a wide band from $14 to $145 with a median of $105 [price_min: $14] [price_max: $145] [price_median: $105], placing the typical product in a mid-to-premium range. It supports this with discounts [has_discounts: yes] and email capture [has_email_capture: yes], while its stated promise of free shipping and returns is only partly reflected in the listed terms [free_shipping_threshold: $100] [free_returns: no].

**Risks**

1. It has a broad, well-organized catalog spanning many categories and collections, so matching its range is difficult [categories: New Arrivals, All, Bestsellers, LEATHER ALTERNATIVES, Men's Shoes, Sneakers, Slip Ons, Sandals] [products_sampled: 50 products from 5 collections].
2. It accepts a very wide set of payment methods, reducing checkout friction for many buyers [payment_methods: American Express, Apple Pay, Discover, Elo, Google Pay, JCB, Mastercard, PayPal, Shop Pay, Visa].
3. It runs discounts and captures emails, giving it levers to convert price-sensitive visitors and re-engage them [has_discounts: yes] [has_email_capture: yes].

**Opportunities**

1. Its free returns are not actually free according to the listed terms, so a competitor offering genuinely free returns can differentiate [free_returns: no] [return_days: 30].
2. Its free shipping only applies from $100, leaving room for a competitor to offer a lower or no threshold [free_shipping_threshold: $100].
3. It has no loyalty program and no referral program, so a competitor could win repeat and word-of-mouth business with either [has_loyalty: no] [has_referral: no].

The business report's methodology line for the same run:

> **LLM step:** `--ai` with DeepSeek, model deepseek-flash. The scanned values for this site (the fields listed in the prompt, no page HTML) were sent to DeepSeek's API (api.deepseek.com). The AI analysis section was written from them. Everything else is rule-based.

## Is it useful?

Mostly not. Compared with the rule-based "Key Insights" printed above it in the same report:

- **Says something the tables do not:** one thing. The store's own description promises "FREE
  shipping & returns", and the scanned terms say free shipping only over $100 and returns not
  free. The rule-based text prints the quote and the terms in separate lines and never puts them
  side by side. The ground truth read by hand confirms the terms (allbirds' returns page: customers
  pay return shipping unless they buy return coverage), so the mismatch is the store's own and not
  a scraping error.
- **Restates the tables:** the price band, the payment methods, email capture, the $100
  threshold, no loyalty or referral program. Each sentence is one row of `report.csv` with
  "a competitor could..." added.
- **Gets things wrong:**
  - It reads "50 products from 5 collections", which is the size of the tool's sample, as the
    breadth of the catalogue, and calls the catalogue "well-organized", which no field says.
  - It counts "runs discounts" as a strength. The rule-based line beside it says 1 of 50 sampled
    products was marked down; the prompt only had `has_discounts: yes`.

Every point cites a real field, as the parser requires, but a correct citation does not make the
sentence correct: the two errors above both cite their fields. For a reader who has the tables,
the AI section adds one useful cross-check and two claims to be careful with.
