"""Email capture is a sign-up for marketing email, not an account form or a menu entry (Phase 5
Batch 2; barefootbuttons: the only email fields are WooCommerce's login / register forms, and its
header "Newsletter" item links to #header-newsletter-signup, which is not on the page)."""

import pytest
from bs4 import BeautifulSoup

from modules.promo_extractor import extract_promotions

REGISTER = """<div class="u-column2 col-2"><h2>Register</h2>
<form method="post" class="woocommerce-form woocommerce-form-register register">
<p><label for="reg_email">Email address</label>
<input type="email" class="woocommerce-Input woocommerce-Input--text input-text" name="email" id="reg_email"></p>
<button type="submit" name="register">Register</button></form></div>"""
LOGIN = """<form class="woocommerce-form woocommerce-form-login login" method="post">
<input type="text" name="username" id="username" autocomplete="username">
<input type="password" name="password" id="password"><button name="login">Log in</button></form>"""
SHOPIFY_LOGIN = """<form method="post" action="/account/login" id="customer_login">
<input type="email" name="customer[email]" id="CustomerEmail"><input type="password" name="customer[password]">
</form>"""
MENU_ITEM = """<ul class="header-nav"><li class="header-newsletter-item has-icon">
<a href="#header-newsletter-signup" class="tooltip"><i class="icon-envelop"></i>
<span class="header-newsletter-title">Newsletter</span></a></li></ul>"""


def _email(body):
    html = f"<html><body><header>{MENU_ITEM if 'MENU' in body else ''}</header>{body.replace('MENU', '')}</body></html>"
    return extract_promotions(BeautifulSoup(html, "html.parser"), html)["has_email_capture"]


def test_account_forms_and_a_menu_item_are_not_email_capture():
    # barefootbuttons: the whole structure together
    assert _email("MENU" + REGISTER + LOGIN) is False


@pytest.mark.parametrize("body", [REGISTER, LOGIN, SHOPIFY_LOGIN, "MENU"])
def test_each_alone_is_not_email_capture(body):
    assert _email(body) is False


@pytest.mark.parametrize("body", [
    # a footer newsletter form (rastaclat, beardbrand)
    '<footer><form action="/contact#contact_form" class="footer__newsletter newsletter-form">'
    '<input type="email" name="contact[email]" placeholder="Email"><button>Subscribe</button></form></footer>',
    # a newsletter block whose form Klaviyo draws (deathwishcoffee)
    '<footer><div class="newsletter center"><h3>Sign up and save 20%</h3>'
    '<div class="klaviyo-form-XyZ12"></div></div></footer>',
    # a register form next to a real signup
    REGISTER + '<form class="mc4wp-form"><input type="email" name="EMAIL"><input type="submit" value="Sign up"></form>',
])
def test_newsletter_signups_still_count(body):
    assert _email(body) is True
