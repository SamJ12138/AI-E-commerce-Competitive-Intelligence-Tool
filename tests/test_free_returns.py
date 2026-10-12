"""free_returns: True when the store says returns are free, False when it says the customer pays (or
returns are not accepted), unknown when it says neither (Phase 5 Batch 2).

Real-store misses: deathwishcoffee and barefootbuttons state nothing and got False; allbirds says
customers pay return shipping and got True from a homepage fallback; beardbrand's FAQ offers a
complimentary return label, but its returns page (no cost wording) was accepted with False."""

import pytest

from modules.policy_extractor import PolicyExtractor
from tests.page_server import analyze_pages, shopify_page


@pytest.mark.parametrize("text", [
    "Return Shipping: Customers are responsible for return shipping charges.",                 # allbirds
    "Please note that the customer is responsible for the cost of the return shipping label.",  # rastaclat
    "All returns are subject to a $9.95 return fee deducted from your refund amount.",         # brooklinen
    "Due to the perishable nature of the product, we cannot accept returned merchandise.",     # porterandyork
    "You will be responsible for paying for your own shipping costs for returning your item.",  # WooCommerce
])
def test_paid_or_no_returns_is_false(text):
    assert PolicyExtractor()._check_free_returns(text.lower()) is False


@pytest.mark.parametrize("text", [
    "We will provide you with a complimentary return label and detailed instructions.",  # beardbrand
    "Free returns within 30 days.",
    "Returns are free for US orders.",
])
def test_free_returns_is_true(text):
    assert PolicyExtractor()._check_free_returns(text.lower()) is True


@pytest.mark.parametrize("text", [
    "Refunds go to the original payment method within 10 business days.",          # nothing about cost
    "Ordering includes several benefits: Pain-free Returns and Exchanges.",         # not "free returns"
    "Free returns on exchanges. Customers are responsible for return shipping on refunds.",  # both
    "Customers are responsible for shipping costs on orders under $50.",            # not about returns
])
def test_nothing_or_mixed_is_unknown(text):
    assert PolicyExtractor()._check_free_returns(text.lower()) is None


def _store(policy_pages, home_extra=""):
    links = "".join(f'<li><a href="{path}">{path}</a></li>' for path in policy_pages)
    pages = {"/": shopify_page(f'<main><h1>Store</h1>{home_extra}</main><footer><ul>{links}</ul></footer>')}
    pages.update({path: shopify_page(f"<main><h1>Policy</h1><p>{text}</p></main>")
                  for path, text in policy_pages.items()})
    return pages


def test_silence_is_unknown_not_false():
    # deathwishcoffee / barefootbuttons: the accepted returns page says nothing about return costs
    intel, _ = analyze_pages(_store({"/policies/refund-policy":
                                     "We offer a 30-day return policy. Refunds go to the original payment method."}))
    assert intel.return_policy.return_days == 30
    assert intel.return_policy.free_returns is None


def test_a_later_page_fills_free_returns():
    # beardbrand: returns page first (window, no cost wording), FAQ with the complimentary label
    intel, _ = analyze_pages(_store({
        "/pages/returns-exchanges": "We offer a 30-day return policy on every order.",
        "/pages/faqs": "We will provide you with a complimentary return label and instructions.",
    }))
    assert intel.return_policy.return_days == 30
    assert intel.return_policy.free_returns is True


def test_a_later_page_with_days_keeps_the_known_value():
    intel, _ = analyze_pages(_store({
        "/pages/faqs": "We will provide you with a complimentary return label and instructions.",
        "/policies/refund-policy": "We offer a 45-day return policy.",
    }))
    assert intel.return_policy.return_days == 45
    assert intel.return_policy.free_returns is True


def test_homepage_fallback_does_not_override_a_policy_page():
    # allbirds: "free shipping" and "free returns" both appear somewhere in the homepage HTML
    home = "<p>Free shipping over $100</p><p>Free returns with Return Coverage at checkout</p>"
    intel, _ = analyze_pages(_store({"/pages/returns-exchanges":
                                     "Our standard return policy is 30 days. Customers are responsible "
                                     "for return shipping charges."}, home))
    assert intel.return_policy.free_returns is False


def test_report_csv_leaves_unknown_free_returns_empty(tmp_path):
    import csv
    from modules.report_writer import ReportWriter
    intel, _ = analyze_pages(_store({"/policies/refund-policy": "We offer a 30-day return policy."}))
    _md, path = ReportWriter(str(tmp_path), language="en").write_full_report([intel], {intel.domain: None})
    row = next(csv.DictReader(open(path, encoding="utf-8-sig")))
    assert row["free_returns"] == "" and row["return_days"] == "30"
