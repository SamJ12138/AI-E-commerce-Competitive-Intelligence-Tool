"""Return-window and free-shipping phrasings found on real stores (Phase 5 Batch 2)."""

import pytest

from modules.policy_extractor import PolicyExtractor


@pytest.mark.parametrize("text, days", [
    ("Most of our products can be returned or exchanged within 365 days.", 365),               # brooklinen
    ("We offer full refunds (including shipping) as long as our payment processor allows it "
     "(usually up to 120 days from the date of purchase).", 120),                              # beardbrand
    ("Full refund up to 120 days from order. Free fragrance swaps anytime.", 120),             # beardbrand PDP
    ("Items can be exchanged within 45 days.", 45),
    ("Our refund and returns policy lasts 14 days.", 14),                                      # unchanged
])
def test_return_window(text, days):
    assert PolicyExtractor()._extract_return_days(text.lower()) == days


@pytest.mark.parametrize("text", [
    "Orders ship within 3 days of purchase confirmation from our warehouse.",
    "Free shipping up to 5 days faster with Prime.",
])
def test_not_a_return_window(text):
    assert PolicyExtractor()._extract_return_days(text.lower()) is None


@pytest.mark.parametrize("text, threshold", [
    ("Luxury shipping is free for US domestic orders over $100 (excludes gift cards).", 100.0),  # beardbrand FAQ
    ("Free luxury shipping on US orders $100+", 100.0),                                          # beardbrand PDP
    ("Shipping is free on all domestic orders over $60.", 60.0),
    ("Free shipping on orders over $50", 50.0),                                                  # unchanged
])
def test_free_shipping_threshold(text, threshold):
    assert PolicyExtractor()._extract_free_shipping_threshold(text.lower()) == threshold
