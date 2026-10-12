"""Free-shipping offers stated on FAQ / help pages (Phase 3 Batch 4; rastaclat /pages/faq,
deathwishcoffee /pages/help): the pages get a place in max_pages and their phrasing is read."""

import pytest
from bs4 import BeautifulSoup

from modules.models import Platform
from modules.policy_extractor import extract_policies
from modules.url_utils import categorize_page_type
from tests.test_discovery import _discover

MENU = [(f"/collections/c{i}", f"Collection {i}") for i in range(25)]
FOOTER = [("/pages/faq", "FAQ"), ("/pages/help", "Help & FAQs"), ("/pages/return-policy", "Return Policy")]


def test_help_pages_are_policy_pages():
    assert categorize_page_type("https://shop.test/pages/help") == "policy"
    assert categorize_page_type("https://shop.test/pages/faq") == "policy"


def test_faq_and_help_pages_get_a_place_in_max_pages():
    pages, _ = _discover(MENU + FOOTER, Platform.SHOPIFY, max_pages=20)
    assert {"/pages/faq", "/pages/help", "/pages/return-policy"} <= set(pages)


@pytest.mark.parametrize("sentence, threshold", [
    # rastaclat's structure: a named service and its delivery window between "free" and "on orders $N+"
    ("United States: Free Speedy(ish) Shipping (Ground, 3-6 business days) on orders $60+. "
     "Speedy Shipping $7.99 for orders under $60.", 60.0),
    # deathwishcoffee's structure: "spend over $N ... free shipping"
    ("Flat-rate shipping is $6.00. If you spend over $40 USD, we will send it with free shipping!", 40.0),
    ("Free shipping on orders over $50", 50.0),
])
def test_faq_phrasings(sentence, threshold):
    html = f"<html><body><h2>Shipping</h2><p>{sentence}</p></body></html>"
    soup = BeautifulSoup(html, "html.parser")
    shipping, _ = extract_policies(soup, soup.get_text(), "policy")
    assert shipping is not None and shipping.free_shipping_threshold == threshold


def test_a_shipping_price_is_not_a_threshold():
    html = "<html><body><p>Standard shipping is $8.00 on orders of any size.</p></body></html>"
    soup = BeautifulSoup(html, "html.parser")
    shipping, _ = extract_policies(soup, soup.get_text(), "policy")
    assert shipping is None or shipping.free_shipping_threshold is None
