# How pages are fetched

This describes what the tool sends to a store and how it decides that a site is `ok`, `blocked` or
`unreachable`. The code is `modules/http_client.py` (the fetch chain) and
`modules/robots_checker.py` (robots.txt).

## 1. robots.txt, once per host

Before the first page of a site, `/robots.txt` is requested with plain `requests` (no per-host delay,
no fallback branch). If it answers 403 or 429, it is asked once more with the tool's own
User-Agent (section 2, step 2).

| robots.txt answer | effect for this run |
|---|---|
| 2xx | The rules of the `User-agent: *` group apply to every URL of the host. |
| 4xx | No rules: every URL is allowed (RFC 9309, "unavailable"). |
| 5xx, timeout, no answer | Every URL of the host is disallowed (RFC 9309, "unreachable"). |

- If the homepage is disallowed, the site is skipped: the console says why (for example
  "robots.txt answered HTTP 503: RFC 9309 says disallow all") and the site does not appear in the
  reports. Other disallowed pages are left out of the crawl.
- `Crawl-delay` in the `*` group: the delay between two requests to that host becomes
  `max(rate_limit_delay, Crawl-delay)`. A log line says so when Crawl-delay is the longer one.
- `--ignore-robots` (or `ignore_robots: true` in the config file) skips all of this: no rules, no
  Crawl-delay.

## 2. Default chain, for every page

Steps 1 and 2 each wait until the host's delay has passed since the previous request to that
host (`rate_limit_delay`, 1.5 s by default, or the Crawl-delay).

1. **`requests` with browser-like headers.** A desktop Chrome User-Agent with the header set a
   browser sends for a page load (`Accept`, `Accept-Language`, `Accept-Encoding`, `sec-ch-ua`,
   `Sec-Fetch-*`, `Upgrade-Insecure-Requests`). `br` is offered in `Accept-Encoding` only when a
   Brotli decoder is installed; a body in an encoding the tool cannot decode is an error, never
   parsed. urllib3 retries 429, 500, 502, 503 and 504 three times with exponential backoff and
   honours `Retry-After`. On a TLS certificate error the request is repeated once without
   certificate verification.
2. **On 403 or 429: the same URL once more with the tool's own User-Agent**
   (`ECI-Tool/1.0 (E-commerce Competitive Intelligence Tool; +https://github.com/SamJ12138/AI-E-commerce-Competitive-Intelligence-Tool)`),
   after the host's delay, with plain `Accept` / `Accept-Language` / `Accept-Encoding` headers and
   none of the browser headers. Some servers refuse browser-like requests that do not come from a
   browser and answer one that says what it is.
3. **On 403: cloudscraper**, if it is installed (it is in `requirements.txt`). It presents itself as
   desktop Chrome on Windows and can answer Cloudflare's JavaScript challenge without a browser. It
   is not tried after a 429.

## 3. With `--render-js`

1. **Headless browser.** Patchright if it is installed, otherwise Playwright; Google Chrome if it is
   installed, otherwise the Chromium that `playwright install chromium` downloads. The page is
   loaded until `DOMContentLoaded`, then the tool waits about 3 seconds for scripts to render and
   reads the resulting HTML. The browser context uses the same Chrome User-Agent and client-hint
   headers as step 2.1, a fixed locale and time zone, and launch options that switch off the
   automation flags a page can read (with plain Playwright, `navigator.webdriver` is also hidden).
   If the browser fails with a network error (`net::ERR_...`, including HTTP/2 protocol errors), the
   page is fetched with step 2.1 instead.
2. **On 403 or any other browser error: cloudscraper**, as in step 2.3.

The tool's-own-User-Agent step is not part of this chain.

## 4. How a site ends

A page counts only if a step returned a 2xx response with a body and no error. A 404 is a missing
page, not content.

| status | when | what the reports say |
|---|---|---|
| `ok` | The homepage was fetched. | Every field is extracted from the pages that were fetched. |
| `blocked` | Every step for the homepage got an HTTP answer and none was usable (403, 429, a challenge page, 404, ...). | "blocked automated access", with the steps tried and their status codes (`requests 403 -> honest-ua 403 -> cloudscraper 403`). Every field is unknown, never guessed; the site is left out of comparisons, averages and recommendations. |
| `unreachable` | No step got an HTTP answer (DNS failure, refused connection, timeout, too many redirects). | "could not be reached"; same treatment as `blocked`. |
| skipped | robots.txt disallows the homepage, or could not be read (section 1). | The site is not in the reports; the console and the run log say why. |

## 5. What is recorded

Every fetch writes one `fetch` event to the run log (`logs/run_<id>.jsonl`): each step tried with
its status, size and duration, the identity it presented (`browser-like headers`, `honest
User-Agent`, `cloudscraper (Chrome)`, `headless browser`), the step that served the page and the
identity that got it. robots.txt answers, the retry of robots.txt and the delay used per host are
`robots` events. The methodology section of `business_report.md` lists, per site, how many pages
were fetched and which step served them. `python scripts/failure_report.py` summarises the newest
run log: failures by stage and error type, and which step served each fetch.
