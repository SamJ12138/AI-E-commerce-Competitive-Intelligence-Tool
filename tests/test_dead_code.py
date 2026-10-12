"""Dead extraction code removed (Phase 5 Batch 4).

policy_evidence.py: only modules/__init__.py re-exported it; nothing used it. price_extractor.py:
a seven-method fallback on the homepage HTML, run only when no product had a price. In every
real-store run log kept from Phases 3-5 only the last method ever produced the range (prices
written in the homepage text); that path moved to product_extractor and was removed in Phase 6
(tests/test_no_price_fallback.py)."""

import importlib.util

import pytest

import modules


@pytest.mark.parametrize("name", ["modules.policy_evidence", "modules.price_extractor"])
def test_module_is_gone(name):
    assert importlib.util.find_spec(name) is None


def test_package_no_longer_exports_them():
    for name in ("PolicyEvidenceLadder", "PolicyEvidence", "EvidenceLevel", "create_blocked_policy_note",
                 "extract_prices_from_js", "extract_price_stats_from_html"):
        assert name not in modules.__all__ and not hasattr(modules, name)
