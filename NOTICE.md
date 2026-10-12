# Notice

No third-party code, data, fonts or images are bundled in this repository. Everything here is
covered by the MIT license in `LICENSE`.

Python dependencies are not vendored: `pip install -r requirements.txt` downloads them from PyPI,
each under its own license. The headless browser used by `--render-js` is downloaded separately by
`playwright install chromium`. The optional LLM step talks to a local Ollama server and model that
you install yourself.

Test fixtures (`tests/fixtures/`) are hand-written pages for made-up stores. They imitate the markup
structure of a Shopify theme, a WooCommerce theme and a Cloudflare challenge page (class names,
element layout) so the extractors can be tested offline; they contain no copied page content, and
the challenge page's tokens are placeholders. Shopify, WooCommerce, Cloudflare, and the payment and
review brands named in fixtures and docs are trademarks of their owners.

`docs/real-corpus/` holds facts read by hand from public store pages (prices, policy terms) with the
URL each came from; no page HTML is kept.
