"""Tests for modules/obs.py and for the exception-audit rule (every handler reports)."""

import ast
import json
from pathlib import Path

import pytest

from modules import obs

REPO = Path(__file__).resolve().parent.parent
SOURCES = [REPO / "main.py"] + sorted(p for p in (REPO / "modules").glob("*.py") if p.name != "obs.py")
IMPORT_TIME_MARK = "obs: import-time"


@pytest.fixture
def run(tmp_path):
    run_id = obs.init_run(log_dir=str(tmp_path), run_id="t")
    yield tmp_path / f"run_{run_id}.jsonl"
    obs.close_run()


def _events(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_noop_without_run(tmp_path):
    obs.close_run()
    obs.event("fetch", "success", url="x")
    obs.note("platform", "Shopify", "regex")
    obs.field("fields", "platform", "Shopify")
    assert not obs.active() and list(tmp_path.iterdir()) == []


def test_event_schema(run):
    obs.set_site("http://127.0.0.1:1")
    obs.event("fetch", "fail", duration_ms=1.234, error_type="blocked", error_message="403", url="u")
    (e,) = _events(run)
    assert set(e) == {"ts", "run_id", "site", "stage", "event", "duration_ms", "error_type",
                      "error_message", "context"}
    assert (e["run_id"], e["site"], e["stage"], e["event"]) == ("t", "http://127.0.0.1:1", "fetch", "fail")
    assert e["error_type"] == "blocked" and e["context"] == {"url": "u"}


def test_unknown_error_type_is_coerced(run):
    obs.event("fetch", "fail", error_type="weird")
    (e,) = _events(run)
    assert e["error_type"] == "unknown" and e["context"]["bad_error_type"] == "weird"


def test_stage_context_manager_logs_fail_and_reraises(run):
    with pytest.raises(ValueError):
        with obs.stage("products"):
            raise ValueError("bad price")
    start, fail = _events(run)
    assert (start["event"], fail["event"], fail["error_type"]) == ("start", "fail", "parse")


def test_field_takes_provenance_from_matching_candidate(run):
    obs.set_site("s")
    obs.note("price_max", 39.0, "selector", "card A", url="/c")
    obs.note("price_max", 49.0, "json_ld", "page B", url="/p")
    obs.field("fields", "price_max", 39.0)
    obs.field("fields", "price_min", None)
    fields = [e["context"] for e in _events(run) if e["context"].get("kind") == "field"]
    assert fields[0]["source"] == "selector" and fields[0]["url"] == "/c"
    assert fields[1]["source"] == "default"


def test_field_prefers_the_applied_candidate(run):
    obs.note("free_shipping_threshold", 50.0, "regex", "homepage promo text")
    obs.apply("free_shipping_threshold", 50.0, "promo threshold applied")
    obs.note("free_shipping_threshold", 50.0, "regex", "homepage JS fallback (not applied)")
    obs.field("fields", "free_shipping_threshold", 50.0)
    detail = _events(run)[-1]["context"]["detail"]
    assert detail.startswith("promo threshold applied") and "homepage promo text" in detail


def test_list_fields_match_regardless_of_order(run):
    obs.note("payment_methods", ["Visa", "PayPal"], "regex", "d")
    obs.field("fields", "payment_methods", ["PayPal", "Visa"])
    assert _events(run)[-1]["context"]["source"] == "regex"


def test_swallowed_uses_active_exception(run):
    try:
        raise TimeoutError("read timed out")
    except TimeoutError:
        obs.swallowed("x.py:f", fallback="None", stage="fetch")
    (e,) = _events(run)
    assert e["error_type"] == "timeout" and e["context"]["swallowed"] is True


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_every_except_handler_reports_to_obs(path):
    """Step 4 rule: no try/except may swallow an error without an obs record."""
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    missing = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.ExceptHandler):
            continue
        if IMPORT_TIME_MARK in lines[node.lineno - 1]:
            continue
        calls = [n for stmt in node.body for n in ast.walk(stmt) if isinstance(n, ast.Call)]
        if not any(isinstance(c.func, ast.Attribute) and isinstance(c.func.value, ast.Name)
                   and c.func.value.id == "obs" for c in calls):
            missing.append(node.lineno)
    assert not missing, f"{path.name}: except handlers without obs.* call at lines {missing}"
