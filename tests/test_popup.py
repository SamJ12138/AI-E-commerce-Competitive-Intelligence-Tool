"""has_popup is a marketing popup: an overlay the store opens by itself to offer a sign-up or a deal
(Phase 6). Before, any element whose class or id contained "popup" or "modal", or the word "klaviyo"
anywhere in the HTML, made it True, and it was True on all seven saved real-store homepages: cart
drawers, quick-buy and search modals, policy modals, a mega menu's class, a login lightbox.

True: a popup with an email / phone field or offer wording, or an exit-intent overlay, in the HTML.
None: none in the HTML, but a script that draws popups in the browser is loaded (Klaviyo onsite,
Attentive, Postscript, ...): without --render-js it cannot be seen. False: neither."""

import json
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from modules.promo_extractor import extract_promotions

# --- not marketing popups (each trimmed from a saved homepage) -------------------------------------
CART_LIGHTBOX = """<div id="cart-popup" class="mfp-hide"><div class="cart-popup-inner inner-padding">
<div class="cart-popup-title text-center"><span class="uppercase">Cart</span></div>
<p class="woocommerce-mini-cart__empty-message">No products in the cart.</p></div></div>"""
LOGIN_LIGHTBOX = """<div id="login-form-popup" class="lightbox-content mfp-hide"><div class="account-container lightbox-inner">
<h3>Login</h3><form class="woocommerce-form woocommerce-form-login login" method="post">
<input type="text" name="username"><input type="password" name="password"><button>Log in</button></form>
<a href="/my-account/lost-password/">Lost your password?</a> <a href="/my-account/">Register</a></div></div>"""
COOKIE_BANNER = """<div id="cmplz-cookiebanner-1-optout" class="cmplz-cookiebanner banner-1" role="dialog" aria-modal="true">
<div class="cmplz-header">Manage Consent</div><div class="cmplz-message">To provide the best experiences, we use
technologies like cookies.</div><button class="cmplz-btn cmplz-accept">Accept</button></div>"""
QUICK_BUY = """<quick-buy-modal id="product-quick-buy-template--1" class="quick-buy-modal modal">
<div class="modal__content">Add to cart - save 20% today</div></quick-buy-modal>"""
CART_DRAWER = """<section id="shopify-section-cart-drawer" class="shopify-section-group-overlay-group">
<cart-drawer class="drawer" role="dialog" aria-modal="true"><p>Your cart is empty</p></cart-drawer></section>"""
SEARCH_MODAL = """<details-modal class="header__search"><div class="search-modal modal__content" role="dialog" aria-modal="true">
<div class="modal-overlay"></div><form class="search search-modal__form" role="search">
<input type="search" id="Search-In-Modal" name="q"></form></div></details-modal>"""
MEGA_MENU = """<nav class="header__inline-menu"><div id="MegaMenu-Content-1" class="mega-menu__content global-settings-popup">
<a href="/collections/subscribe">Subscribe &amp; Save</a><a href="/collections/bundles">Save Up to 15% Off</a></div></nav>"""
POLICY_MODAL = """<div id="modal-refund-policy" class="z-takeover fixed inset-0" role="dialog" aria-modal="true">
<button>Close</button><h2>Refund policy</h2><p>Sign up for an account to start a return. Offer codes are not refundable.</p></div>"""
ADDED_TO_CART = """<div id="shopify-section-header__post_atc_modal_section" class="shopify-section post-atc-modal-section">
<div class="z-takeover fixed inset-0" role="dialog" aria-modal="true">Added to Cart
Spend more to earn free shipping! Save on shipping.</div></div>"""
COUNTRY_SELECTOR = """<div id="shopify-section-footer__geofencing" class="shopify-section"><div class="geofencing-modal modal">
<button>Close</button>Where are we shipping to? Purchasing from your country's website is the best way to save on duties.</div></div>"""
ACCOUNT_DROPDOWN = """<div id="header-account-dropdown" class="header__account-dropdown" role="dialog">
<a href="/account/register">Claim Your Offer</a><a href="/account/register">Create Account</a></div>"""
GIFT_APP = """<div id="freegifts-main-popup-container" class="freegifts-main-container sca-modal-fg"></div>
<div id="bogos-mix-match-main-collection-popup-container" class="sca-modal-fg"></div>"""
DISABLED_THEME_POPUP = """<div class="shopify-section mount-popup" id="shopify-section-popup">
<modal-box class="popup" data-options='{ "show": 10, "frequency": "day", "enabled": false }' id="modal-popup" style="display:none">
<div class="popup-content"><div class="popup-text">Sign up and get 10% off your first order</div>
<form><input type="email" name="contact[email]"></form></div></modal-box></div>"""
INLINE_NEWSLETTER = """<div class="newsletter center"><h2>STAY BOLD. SIGN UP AND SAVE 20% OFF YOUR FIRST ORDER</h2>
<div class="klaviyo-form-RpC5ka"></div></div>"""

NOT_POPUPS = {"cart lightbox": CART_LIGHTBOX, "login lightbox": LOGIN_LIGHTBOX, "cookie banner": COOKIE_BANNER,
              "quick-buy modal": QUICK_BUY, "cart drawer": CART_DRAWER, "search modal": SEARCH_MODAL,
              "mega menu": MEGA_MENU, "policy modal": POLICY_MODAL, "added to cart": ADDED_TO_CART,
              "country selector": COUNTRY_SELECTOR, "account dropdown": ACCOUNT_DROPDOWN, "gift app": GIFT_APP,
              "disabled theme popup": DISABLED_THEME_POPUP, "inline newsletter": INLINE_NEWSLETTER}

# --- marketing popups ------------------------------------------------------------------------------
EXIT_OVERLAY = """<div id="overlayModal" class="js-exit-overlay" data-dy-id="overlayModal"><div class="modal">
<button class="overlay_close close close--x"></button><p class="h4 headline">Hold Up!<br> Stop Right There.</p>
<div class="button button--primary cta close"><a href="#">Start Saving Now</a></div></div></div>"""
NEWSLETTER_POPUP = """<div id="pum-412" class="pum pum-overlay pum-theme-lightbox popmake-overlay auto_open" role="dialog"
aria-modal="false" data-popup-id="412" data-popup-settings='{"triggers":[{"type":"auto_open","settings":{"delay":"5000"}}]}'>
<div id="popmake-412" class="pum-container popmake theme-lightbox"><div class="pum-content popmake-content">
<h2>Join the list</h2><p>Early access to new arrivals and sales.</p>
<form><input type="email" name="EMAIL" placeholder="Email address"><input type="submit" value="Subscribe"></form>
</div><button class="pum-close popmake-close">Close</button></div></div>"""
SMS_POPUP = """<div class="sms-modal" role="dialog" aria-modal="true"><h2>Text me deals</h2>
<input type="tel" name="phone"><button>Get my code</button></div>"""

# --- scripts that draw popups in the browser --------------------------------------------------------
KLAVIYO = '<script async src="https://static.klaviyo.com/onsite/js/AbC123/klaviyo.js?company_id=AbC123"></script>'
ATTENTIVE = '<script src="https://cdn.attn.tv/store/dtag.js" defer></script>'
POSTSCRIPT = '<script src="https://sdk.postscript.io/sdk-script-loader.bundle.js?shopId=1"></script>'
# allbirds: Attentive loaded by Shopify's inline asyncLoad list (escaped slashes), no <script src> of its own
ATTENTIVE_LOADER = (r'<script>(function() { function asyncLoad() { var urls = ["https:\/\/cdn.attn.tv\/store\/dtag.js'
                    '?shop=store.myshopify.com"]; for (var i = 0; i < urls.length; i++) { var s = document.createElement('
                    '"script"); s.src = urls[i]; document.head.appendChild(s); } } asyncLoad(); })();</script>')


def _popup(body):
    html = f"<html><head><title>Store</title></head><body>{body}</body></html>"
    return extract_promotions(BeautifulSoup(html, "lxml"), html)["has_popup"]


@pytest.mark.parametrize("name", NOT_POPUPS)
def test_functional_overlays_are_not_marketing_popups(name):
    assert _popup(NOT_POPUPS[name]) is False


def test_all_of_them_together_are_not_a_popup():
    assert _popup("".join(NOT_POPUPS.values())) is False


@pytest.mark.parametrize("body", [EXIT_OVERLAY, NEWSLETTER_POPUP, SMS_POPUP], ids=["exit", "newsletter", "sms"])
def test_marketing_popups(body):
    assert _popup(CART_LIGHTBOX + body + SEARCH_MODAL) is True


@pytest.mark.parametrize("script", [KLAVIYO, ATTENTIVE, POSTSCRIPT, ATTENTIVE_LOADER],
                         ids=["klaviyo", "attentive", "postscript", "attentive-inline-loader"])
def test_popup_script_alone_is_unknown(script):
    assert _popup(INLINE_NEWSLETTER + DISABLED_THEME_POPUP + script) is None


def test_popup_in_the_html_wins_over_the_script():
    assert _popup(KLAVIYO + EXIT_OVERLAY) is True


def test_the_word_klaviyo_alone_is_not_a_script():
    assert _popup('<p>We moved our email list to klaviyo last year.</p>') is False


def test_unknown_popup_in_reports(tmp_path):
    """None reads as unknown: empty CSV cell, no 'Popup' tactic, 'unknown' in the pressure inputs."""
    import csv
    from modules.pressure_score import format_input, score_pressure
    from modules.report_writer import ReportWriter
    from tests.page_server import analyze_pages, shopify_page
    intel, _ = analyze_pages({"/": shopify_page(KLAVIYO + "<main><h1>Store</h1></main>")})
    assert intel.has_popup is None
    md, csv_path = ReportWriter(str(tmp_path), language="en").write_full_report([intel], {intel.domain: None})
    row = next(csv.DictReader(open(csv_path, encoding="utf-8-sig")))
    assert row["has_popup"] == ""
    assert "Popup" not in Path(md).read_text(encoding="utf-8")
    marketing = next(f for f in score_pressure(intel)["factors"] if f["key"] == "marketing_sophistication")
    assert format_input("has_popup", marketing["inputs"]["has_popup"], "en") == "popup unknown"


def test_woocommerce_fixture_has_a_popup():
    root = Path(__file__).parent / "fixtures" / "stores"
    expected = {s: json.loads((root / s / "fixtures.json").read_text(encoding="utf-8"))["expected"]["has_popup"]
                for s in ("shopify_basic", "woocommerce_promo", "blocked")}
    assert expected == {"shopify_basic": False, "woocommerce_promo": True, "blocked": None}


def test_real_corpus_scores_has_popup():
    import importlib.util
    spec = importlib.util.spec_from_file_location("real_corpus", Path(__file__).parent.parent / "scripts" / "real_corpus.py")
    rc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rc)
    assert rc.FIELDS["has_popup"] == ("has_popup", "has_popup", "bool")
    assert "has_popup" in rc.ORDER
    truth = rc.load_truth()
    assert set(truth) >= {"allbirds", "barefootbuttons", "beardbrand", "brooklinen", "deathwishcoffee",
                          "porterandyork", "rastaclat"}
    assert all("has_popup" in t["fields"] for t in truth.values())


def test_page_state_classes_on_body_do_not_hide_a_popup():
    # brooklinen rendered with --render-js: <body class="truemed-enabled swym-loading">
    html = f'<html class="js menu-open"><body class="truemed-enabled swym-loading cart-empty">{EXIT_OVERLAY}</body></html>'
    assert extract_promotions(BeautifulSoup(html, "lxml"), html)["has_popup"] is True
