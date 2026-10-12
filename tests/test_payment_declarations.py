"""Shopify payment declarations in markup (Phase 3 Batch 4; all four Shopify stores in the corpus):
the Apple Pay merchant config, the PayPal metadata's Venmo flag and the <link rel="buy"> wallets."""

import pytest
from bs4 import BeautifulSoup

from modules.trust_extractor import TrustExtractor

# Hand-written <head> fragment with the structure the four stores serve (values are made up).
HEAD = """<html><head>
<script id="apple-pay-shop-capabilities" type="application/json">{"shopId":101,"countryCode":"US",
"currencyCode":"USD","merchantCapabilities":["supports3DS"],"merchantName":"Lantern Row",
"supportedNetworks":["visa","masterCard","discover","amex","elo","jcb"],"shopifyPaymentsEnabled":true}</script>
<meta id="in-context-paypal-metadata" data-shop-id="101" data-venmo-supported="{venmo}"
 data-environment="production" data-locale="en_US" data-paypal-v4="true" data-currency="USD">
<link rel="buy" href="/cart/1:1" payment="dev.shopify.shop_pay com.google.pay dev.shopify.card">
</head><body><h1>Cedar Candle</h1></body></html>"""

DECLARED = {"Shop Pay", "Apple Pay", "Google Pay", "PayPal", "Visa", "Mastercard", "American Express",
            "Discover", "JCB", "Elo"}


def _methods(html):
    return set(TrustExtractor()._detect_payment_methods(BeautifulSoup(html, "html.parser"), html))


def test_declared_methods_without_venmo():
    assert _methods(HEAD.replace("{venmo}", "false")) == DECLARED


def test_venmo_only_when_the_flag_is_true():
    assert _methods(HEAD.replace("{venmo}", "true")) == DECLARED | {"Venmo"}


@pytest.mark.parametrize("token, method", [("com.google.pay", "Google Pay"),
                                            ("dev.shopify.shop_pay", "Shop Pay"),
                                            ("com.apple.pay", "Apple Pay")])
def test_link_rel_buy_wallets(token, method):
    html = f'<html><head><link rel="buy" href="/cart/1:1" payment="{token}"></head><body></body></html>'
    assert method in _methods(html)


def test_venmo_named_on_the_page_still_counts():
    assert "Venmo" in _methods("<html><body><p>We accept Venmo and PayPal.</p></body></html>")


# A store whose wallets are declared only on product pages (as on the four Shopify stores).
PAGES = {
    "/": """<html><head><script>var Shopify = {}; Shopify.theme = {"name":"Dawn"};</script>
<meta id="in-context-paypal-metadata" data-venmo-supported="false"></head><body>
<a href="/products/cedar-candle">Cedar Candle</a></body></html>""",
    "/products/cedar-candle": """<html><head><script>var Shopify = {}; Shopify.theme = {"name":"Dawn"};</script>
<link rel="buy" href="/cart/1:1" payment="dev.shopify.shop_pay com.google.pay dev.shopify.card"></head>
<body><h1>Cedar Candle</h1><div class="price"><span class="price-item price-item--regular">$28.00</span></div>
</body></html>""",
    "/robots.txt": "User-agent: *\nDisallow: /cart\n",
}


def test_wallets_declared_on_product_pages_are_kept():
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    import main
    from modules.http_client import HttpClient
    from modules.models import Config
    from modules.robots_checker import RobotsChecker

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = PAGES.get(self.path.rstrip("/") or "/")
            self.send_response(200 if body else 404)
            self.send_header("Content-Type", "text/plain" if self.path.endswith(".txt") else "text/html")
            self.end_headers()
            if body:
                self.wfile.write(body.encode())

        def log_message(self, *args):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    cfg = Config(rate_limit_delay=0, timeout=10)
    client = HttpClient(cfg)
    try:
        intel = main.analyze_site(f"http://127.0.0.1:{srv.server_address[1]}", client, RobotsChecker(cfg), cfg)
    finally:
        client.close()
        srv.shutdown()
        srv.server_close()
    assert {"Shop Pay", "Google Pay", "PayPal"} <= set(intel.payment_methods)
    assert "Venmo" not in intel.payment_methods


def test_brand_words_inside_styles_and_scripts_do_not_count():
    # porterandyork: WooCommerce's inline CSS styles card-brand icons; deathwishcoffee: an analytics
    # script lists payment domains to ignore as referrers.
    html = """<html><head>
<style>.wc-credit-card-form-card-cvc.visa,.wc-credit-card-form-card-cvc.mastercard,
.wc-credit-card-form-card-cvc.amex{background-size:32px}</style>
<script>var cfg = {"referralExclusion":"/(paypal|visa|MasterCard|portal\\.afterpay\\.com)/"};</script>
</head><body><h1>Flank Steak</h1><p>$39</p></body></html>"""
    assert _methods(html) == set()


def test_payment_icons_in_markup_still_count():
    html = """<html><body><footer><ul class="list-payment">
<li><svg aria-labelledby="pi-visa" class="icon icon--full-color"><title id="pi-visa">Visa</title></svg></li>
<li><svg aria-labelledby="pi-paypal"><title id="pi-paypal">PayPal</title></svg></li>
</ul></footer></body></html>"""
    assert _methods(html) == {"Visa", "PayPal"}
