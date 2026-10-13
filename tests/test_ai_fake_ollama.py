"""The --ai step end to end with a fake Ollama client (Phase 5 Batch 3, one call per store since
Phase 8). Ollama itself is not installed on the machine where this was written, so the Ollama path
is verified only against this fake: main.py runs on two fixture stores with --ai and
ai_provider: ollama, a stand-in `ollama` module records every chat call, and the test checks what
the model is asked and where its answer lands in the reports."""

import csv
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import StoreServer

REPO = Path(__file__).resolve().parent.parent
MODEL = "fake-model:1"
# The answer shape the prompt asks for; the cited fields are ones every analysed store has
ANSWER = "\n".join([
    "## Positioning", "FAKE-POSITIONING [platform: Shopify]", "",
    "## Risks", "1. FAKE-RISK-ONE [platform: Shopify]", "2. FAKE-RISK-TWO [domain: x]",
    "3. FAKE-RISK-THREE [platform: Shopify]", "",
    "## Opportunities", "1. FAKE-OPP-ONE [platform: Shopify]", "2. FAKE-OPP-TWO [domain: x]",
    "3. FAKE-OPP-THREE [platform: Shopify]", ""])

# A stand-in for the `ollama` package: list() offers MODEL, chat() records the call and answers.
BOOTSTRAP = r'''
import json, os, runpy, sys, types
fake = types.ModuleType("ollama")
calls = []
def _list():
    return {"models": [{"name": os.environ["FAKE_MODEL"]}]}
def _chat(model, messages, options=None):
    calls.append({"model": model, "messages": messages})
    with open(os.environ["FAKE_OLLAMA_LOG"], "w", encoding="utf-8") as f:
        json.dump(calls, f, ensure_ascii=False)
    return {"message": {"content": os.environ["FAKE_ANSWER"]}, "prompt_eval_count": 321, "eval_count": 54,
            "done_reason": "stop"}
fake.list, fake.chat = _list, _chat
sys.modules["ollama"] = fake
sys.argv = ["main.py"] + sys.argv[1:]
runpy.run_path("main.py", run_name="__main__")
'''


@pytest.fixture(scope="module")
def ai_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("ai_run")
    servers = [StoreServer(name).start() for name in ("shopify_basic", "blocked")]
    try:
        (out / "sites.txt").write_text("".join(s.base_url + "\n" for s in servers), encoding="utf-8")
        (out / "config.yaml").write_text(f"rate_limit_delay: 0\nai_provider: ollama\n"
                                         f"db_path: {(out / 'intel.db').as_posix()}\n", encoding="utf-8")
        env = dict(os.environ, ECI_LOG_DIR=str(out / "logs"), PYTHONIOENCODING="utf-8", FAKE_MODEL=MODEL,
                   FAKE_OLLAMA_LOG=str(out / "ollama_calls.json"), FAKE_ANSWER=ANSWER)
        proc = subprocess.run([sys.executable, "-c", BOOTSTRAP, "--sites", str(out / "sites.txt"),
                               "--outdir", str(out), "--config", str(out / "config.yaml"), "--lang", "en",
                               "--ai", "--ai-model", MODEL],
                              cwd=REPO, env=env, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=300)
    finally:
        for s in servers:
            s.stop()
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    calls = json.loads((out / "ollama_calls.json").read_text(encoding="utf-8"))
    rows = {r["domain"]: r for r in csv.DictReader(open(out / "report.csv", encoding="utf-8-sig"))}
    log = [json.loads(line) for p in (out / "logs").glob("run_*.jsonl")
           for line in p.read_text(encoding="utf-8").splitlines()]
    return {"out": out, "calls": calls, "rows": rows, "log": log, "servers": [s.base_url for s in servers]}


def _facts(prompt):
    return dict(line[2:].split(": ", 1) for line in prompt.splitlines() if line.startswith("- ") and ": " in line)


def test_the_model_is_asked_once_for_the_store_that_was_read(ai_run):
    (call,) = ai_run["calls"]          # none for the blocked store
    assert call["model"] == MODEL
    assert ai_run["servers"][0].split("//")[1] in call["messages"][-1]["content"]


def test_prompt_carries_only_fields_the_pipeline_produced(ai_run):
    from modules.ai_analyzer import PROMPT_FIELDS
    prompt = ai_run["calls"][0]["messages"][-1]["content"]
    facts = _facts(prompt)
    assert set(facts) <= set(PROMPT_FIELDS), set(facts) - set(PROMPT_FIELDS)
    assert "N/A" not in prompt and "None" not in prompt
    row = next(r for r in ai_run["rows"].values() if r["status"] == "ok")
    # each value is the one the pipeline reported for the store (report.csv)
    assert facts["domain"] == row["domain"]
    assert facts["platform"] == row["platform"]
    assert facts["price_min"] == f"${float(row['price_min']):g}"
    assert facts["price_max"] == f"${float(row['price_max']):g}"
    assert facts["free_shipping_threshold"] == f"${float(row['free_shipping_threshold']):g}"
    assert facts["return_days"] == row["return_days"]
    assert facts["free_returns"] == {"True": "yes", "False": "no"}[row["free_returns"]]
    assert facts["review_platform"] == row["review_platform"]
    assert facts["payment_methods"] == row["payment_methods"].replace("; ", ", ")
    assert facts["has_email_capture"] == {"True": "yes", "False": "no"}[row["has_email_capture"]]
    # a value the pipeline did not produce is left out, not filled in
    assert row["review_count"] == "" and "review_count" not in facts


def test_the_call_is_logged_with_tokens_and_without_the_prompt(ai_run):
    (e,) = [e for e in ai_run["log"] if e["context"].get("kind") == "ai_call"]
    assert e["event"] == "success"
    assert (e["context"]["provider"], e["context"]["model"]) == ("ollama", MODEL)
    assert (e["context"]["prompt_tokens"], e["context"]["completion_tokens"]) == (321, 54)
    assert "Answer with exactly these three sections" not in json.dumps(ai_run["log"], ensure_ascii=False)


def test_report_prints_the_answer_in_the_ai_section_of_that_store(ai_run):
    md = (ai_run["out"] / "report.md").read_text(encoding="utf-8")
    ok_host, blocked_host = (u.split("//")[1] for u in ai_run["servers"])
    blocked_at = md.index(f"## 🏪 {blocked_host}")
    ok_section = md[md.index(f"## 🏪 {ok_host}"):blocked_at]
    title = ok_section.index(f"AI analysis (ollama / {MODEL})")
    assert ok_section.index("Key Insights") < title     # the rule-based text stays, before it
    order = ["FAKE-POSITIONING", "FAKE-RISK-ONE", "FAKE-RISK-THREE", "FAKE-OPP-ONE", "FAKE-OPP-THREE"]
    positions = [ok_section.index(word) for word in order]
    assert title < positions[0] and positions == sorted(positions)
    # nothing from the model in the blocked store's section
    assert "FAKE-" not in md[blocked_at:]


def test_business_report_names_provider_model_and_where_the_data_went(ai_run):
    biz = (ai_run["out"] / "business_report.md").read_text(encoding="utf-8")
    assert f"AI analysis (ollama / {MODEL})" in biz and "FAKE-RISK-ONE" in biz
    method = biz.split("### Methodology", 1)[1]
    assert f"Ollama, model {MODEL}" in method and "did not leave this machine" in method
