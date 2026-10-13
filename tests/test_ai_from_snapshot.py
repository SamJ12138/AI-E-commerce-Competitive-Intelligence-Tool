"""scripts/ai_from_snapshot.py: the reports rebuilt from a stored scan with the AI step, no fetch."""

import json
import sys
from pathlib import Path

import pytest

from modules import ai_analyzer
from modules.snapshot_store import SnapshotStore

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

ANSWER = "\n".join([
    "## Positioning", "SNAP-POSITIONING [platform: Shopify]", "",
    "## Risks", "1. SNAP-R1 [platform: Shopify]", "2. SNAP-R2 [platform: Shopify]", "3. SNAP-R3 [platform: Shopify]", "",
    "## Opportunities", "1. SNAP-O1 [platform: Shopify]", "2. SNAP-O2 [platform: Shopify]",
    "3. SNAP-O3 [platform: Shopify]"])


class FakeProvider:
    name, model = "deepseek", "deepseek-flash"

    def __init__(self):
        self.calls = 0

    def is_available(self):
        return True

    def chat(self, system, user):
        self.calls += 1
        return ai_analyzer.ChatResult(ANSWER, prompt_tokens=700, completion_tokens=300, finish_reason="stop",
                                      cache_hit_tokens=0)


@pytest.fixture
def snapshot_db(tmp_path, analyzed):
    db = tmp_path / "intel.db"
    SnapshotStore(str(db)).save_snapshot(analyzed["shopify_basic"])
    return db, analyzed["shopify_basic"]


def test_rebuild_runs_the_ai_step_on_the_stored_scan(tmp_path, snapshot_db, monkeypatch):
    import ai_from_snapshot
    import requests
    # nothing may be fetched: the scan comes from the database
    monkeypatch.setattr(requests.Session, "request", lambda *a, **k: pytest.fail("network call"))
    db, intel = snapshot_db
    provider = FakeProvider()
    out = tmp_path / "out"
    summary = ai_from_snapshot.rebuild(db, out, "en", ai_analyzer.AIAnalyzer(provider=provider, language="en"))
    assert provider.calls == 1
    (site,) = summary["sites"]
    assert site["domain"] == intel.domain and site["scan_timestamp"].startswith(intel.scan_timestamp.isoformat()[:16])
    call = site["ai_call"]
    assert (call["provider"], call["model"], call["prompt_tokens"], call["completion_tokens"]) == (
        "deepseek", "deepseek-flash", 700, 300)
    assert call["event"] == "success" and call["latency_ms"] >= 0
    assert set(site["facts"]) <= set(ai_analyzer.PROMPT_FIELDS)
    md = (out / "report.md").read_text(encoding="utf-8")
    biz = (out / "business_report.md").read_text(encoding="utf-8")
    for text in (md, biz):
        assert "AI analysis (deepseek / deepseek-flash)" in text and "SNAP-O3" in text
    assert "sent to DeepSeek" in biz
    # the report is dated with the scan, not with today
    assert intel.scan_timestamp.strftime("%B %d, %Y").replace(" 0", " ") in biz
    assert json.loads((out / "ai_run.json").read_text(encoding="utf-8")) == summary


def test_summary_never_holds_the_prompt_text(tmp_path, snapshot_db):
    import ai_from_snapshot
    db, _ = snapshot_db
    summary = ai_from_snapshot.rebuild(db, tmp_path / "out", "en",
                                       ai_analyzer.AIAnalyzer(provider=FakeProvider(), language="en"))
    assert "Answer with exactly these three sections" not in json.dumps(summary)
