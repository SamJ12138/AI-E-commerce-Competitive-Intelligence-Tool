"""Privacy / terms / cookie text embedded in a page is not promotion wording (Phase 5 Batch 2;
allbirds: its homepage carries the privacy policy in a hidden modal, and "participate in promotions
or loyalty programs" there was read as a loyalty program)."""

from bs4 import BeautifulSoup

from modules.promo_extractor import extract_promotions

MODAL = """<div id="modal-privacy-policy" class="z-takeover fixed inset-0 hidden"><div><p><span>We use
your information when you register to receive communications over email, participate in promotions
or loyalty programs, or refer a friend.</span></p></div></div>"""
TERMS = """<div id="modal-terms-of-service" class="fixed hidden"><p>Rewards points programs, if any, are
governed by these terms. Refer a friend offers are subject to change.</p></div>"""
COOKIE = """<div class="cookie-consent-banner"><p>We and our partners use cookies for loyalty programs and
analytics.</p></div>"""


def _promos(body):
    html = f"<html><body class='cookie-consent-active'><main><h1>Shoes</h1></main>{body}</body></html>"
    return extract_promotions(BeautifulSoup(html, "html.parser"), html)


def test_privacy_modal_is_not_a_loyalty_program():
    assert _promos(MODAL)["has_loyalty_program"] is False


def test_terms_and_cookie_text_are_not_programs():
    r = _promos(TERMS + COOKIE)
    assert r["has_loyalty_program"] is False
    assert r["has_referral_program"] is False


def test_privacy_modal_is_not_a_referral_program():
    assert _promos(MODAL)["has_referral_program"] is False


def test_program_wording_outside_legal_text_still_counts():
    r = _promos(MODAL + '<section class="rewards"><h2>Join our loyalty program</h2>'
                        '<p>Refer a friend and get $10.</p></section>')
    assert r["has_loyalty_program"] is True
    assert r["has_referral_program"] is True
