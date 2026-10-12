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
