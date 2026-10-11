# Failure report

Logs: docs/baseline/logs/run_shopify_basic-20261011T193101.jsonl, docs/baseline/logs/run_woocommerce_promo-20261011T193140.jsonl, docs/baseline/logs/run_blocked-20261011T193216.jsonl, docs/baseline/logs/run_blocked_render_js-20261011T193219.jsonl

Runs: 4 (blocked-20261011T193216, blocked_render_js-20261011T193219, shopify_basic-20261011T193101, woocommerce_promo-20261011T193140) | sites: 4 | events: 381

## 1. Pipeline failures (stage x error_type)

| stage | http | blocked | total |
| --- | --- | --- | --- |
| fetch | 41 | 2 | 43 |
| fetch_homepage |  | 2 | 2 |
| policies | 26 |  | 26 |
| products | 8 |  | 8 |
| robots |  | 2 | 2 |
| **total** | 75 | 6 | 81 |

`fetch` counts every HTTP call that returned an error; `products` / `policies` count the same failed page fetches again at page level (one row per page the pipeline wanted).

## 2. Swallowed exceptions and silent fallbacks (stage x error_type)

| stage | input_invalid | http | blocked | parse | unknown | total |
| --- | --- | --- | --- | --- | --- | --- |
| discovery |  | 6 |  |  | 2 | 8 |
| fetch |  |  |  |  | 4 | 4 |
| fetch_homepage |  |  | 2 |  |  | 2 |
| policies |  |  |  | 1 |  | 1 |
| products |  | 1 |  |  |  | 1 |
| robots |  |  | 2 |  |  | 2 |
| run | 4 |  |  |  |  | 4 |
| site | 4 |  |  |  |  | 4 |
| **total** | 8 | 7 | 4 | 1 | 6 | 26 |

Most frequent locations:

| count | where | error_type | message (truncated) | fallback |
| --- | --- | --- | --- | --- |
| 8 | url_utils.py:extract_domain | input_invalid | no public suffix (IP address or local host): port and subdomain dropped | domain='127.0.0.1' |
| 6 | page_discovery.py:_fetch_sitemap | http | Page not found (404) | [] |
| 4 | http_client.py:<import> | unknown | patchright not importable | browser engine = playwright |
| 2 | page_discovery.py:discover | unknown | 22 guessed/sitemap pages already >= max_pages=20 | homepage links are never crawled |
| 2 | robots_checker.py:_fetch_robots | blocked | robots.txt answered 403 | treat every URL as allowed |
| 2 | main.py:analyze_site | blocked | homepage fetch failed; analysis stops here | SiteIntelligence with defaults is still saved and reported (and AI-scored with --ai) |
| 1 | main.py:analyze_site | http | products.json unavailable: Page not found (404) | HTML pages only |
| 1 | main.py:analyze_site | parse | no shipping policy parsed from any page | ad-hoc ShippingPolicy from homepage promo threshold, regions=['United States'] |

## 3. Skipped stages

| count | stage | kind | reason |
| --- | --- | --- | --- |
| 4 | change_diff |  | --monitor not set |
| 4 | ai |  | --ai not set |
| 1 | policies | shipping_policy_ignored | a policy is already set and this page has no threshold |

## 4. Per-stage latency (ms, events with a duration)

| stage | n | p50 | p95 | max | total s |
| --- | --- | --- | --- | --- | --- |
| brand | 2 | 6.7 | 6.9 | 6.9 | 0.0 |
| categories | 2 | 7.0 | 8.2 | 8.2 | 0.0 |
| discovery | 2 | 4460.9 | 4476.6 | 4476.6 | 8.9 |
| fetch | 51 | 1496.3 | 1523.1 | 3864.8 | 74.3 |
| fetch_homepage | 4 | 18.7 | 3864.8 | 3864.8 | 3.9 |
| load | 4 | 1.0 | 1.0 | 1.0 | 0.0 |
| platform | 2 | 1509.8 | 1518.0 | 1518.0 | 3.0 |
| policies | 2 | 0.9 | 1.6 | 1.6 | 0.0 |
| products | 2 | 28480.9 | 29994.9 | 29994.9 | 58.5 |
| promos | 2 | 12.3 | 23.0 | 23.0 | 0.0 |
| report | 4 | 4.9 | 5.0 | 5.0 | 0.0 |
| robots | 8 | 4.1 | 27.0 | 27.0 | 0.1 |
| site | 4 | 3885.4 | 36048.2 | 36048.2 | 74.5 |
| snapshot | 4 | 13.1 | 14.6 | 14.6 | 0.1 |
| trust | 2 | 3.6 | 3.7 | 3.7 | 0.0 |

`fetch` durations include the per-domain rate-limit wait (`rate_limit_wait_ms`); pipeline stages include the fetches they trigger.

## 5. Fetches

| served_by | status | event | count |
| --- | --- | --- | --- |
| requests | 404 | fail | 41 |
| requests | 200 | success | 8 |
| cloudscraper | 403 | fail | 2 |

Branch chains:

| chain | count |
| --- | --- |
| requests(404) | 41 |
| requests(200) | 8 |
| requests(403) -> cloudscraper(403) | 1 |
| browser(403) -> cloudscraper(403) | 1 |

Total rate-limit wait across fetches: 69.7 s

