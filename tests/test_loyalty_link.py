"""A link to the store's own rewards / loyalty page is a loyalty program (Phase 5 Batch 2;
brooklinen links "/pages/rewards" from its account menu and footer as "Brooklinen Rewards", and the
homepage has no other loyalty wording)."""

import pytest
from bs4 import BeautifulSoup

from modules.promo_extractor import extract_promotions


def _loyalty(body):
    html = f"<html><body><main><h1>Bedding</h1></main>{body}</body></html>"
    return extract_promotions(BeautifulSoup(html, "html.parser"), html)["has_loyalty_program"]


@pytest.mark.parametrize("link", [
    '<footer><ul><li><a href="/pages/rewards"><span>Brooklinen Rewards</span></a></li></ul></footer>',  # brooklinen
    '<a href="/pages/rewards"><svg aria-label="account-my-rewards"></svg></a>',                         # icon only
    '<a href="https://shop.example/pages/ritual-rewards">Ritual Rewards</a>',                            # deathwishcoffee
    '<a href="/account/loyalty">Members</a>',
])
def test_link_to_a_rewards_page(link):
    assert _loyalty(link) is True


@pytest.mark.parametrize("link", [
    '<a href="/products/rewards-luxe-pillowcases">Luxe Pillowcases</a>',   # a product named "rewards-..."
    '<a href="/collections/rewards">Gift ideas</a>',
    '<a href="/blogs/news/the-rewards-of-sleep">Read more</a>',
    '<a href="/pages/faq">FAQ</a>',
])
def test_other_links_are_not(link):
    assert _loyalty(link) is False
