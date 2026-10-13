"""The --ai step end to end with a fake Ollama client (Phase 5 Batch 3). Ollama itself was not
installed on the machine where this was written, so the step is verified only against this fake:
main.py runs on two fixture stores with --ai, a stand-in `ollama` module records every chat call,
and the test checks what the model is asked and where its answer lands in the reports."""

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
INSIGHTS = "## 关键洞察\n- FAKE-INSIGHT-ONE\n- FAKE-INSIGHT-TWO\n\n## 可复制的动作建议\n1. FAKE-ACTION-ONE\n"
POSITIONING = "FAKE-POSITIONING-TEXT"

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
    prompt = messages[-1]["content"]
    return {"message": {"content": os.environ["FAKE_INSIGHTS"] if "关键洞察" in prompt else os.environ["FAKE_POSITIONING"]}}
fake.list, fake.chat = _list, _chat
sys.modules["ollama"] = fake
sys.argv = ["main.py"] + sys.argv[1:]
runpy.run_path("main.py", run_name="__main__")
'''

# Every label the insight prompt can carry, and the pipeline field each one comes from
PROMPT_FIELDS = {
    "网站域名": "domain", "电商平台": "platform", "品牌名称": "brand_name", "品牌定位（页面原文）": "brand_positioning",
    "产品品类": "categories", "价格区间": "price_min/price_max", "中位价格": "price_median", "货币": "currency",
    "有折扣促销": "has_discounts", "公告栏内容": "announcement_bar", "有弹窗": "has_popup",
    "邮件订阅": "has_email_capture", "会员计划": "has_loyalty", "推荐计划": "has_referral",
    "免运费门槛": "free_shipping_threshold", "退货天数": "return_days", "免费退货": "free_returns",
    "评论平台": "review_platform", "评论数量": "review_count", "支付方式": "payment_methods",
}


@pytest.fixture(scope="module")
def ai_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("ai_run")
    servers = [StoreServer(name).start() for name in ("shopify_basic", "blocked")]
    try:
        (out / "sites.txt").write_text("".join(s.base_url + "\n" for s in servers), encoding="utf-8")
        (out / "config.yaml").write_text(f"rate_limit_delay: 0\nai_provider: ollama\n"
                                         f"db_path: {(out / 'intel.db').as_posix()}\n", encoding="utf-8")
        env = dict(os.environ, ECI_LOG_DIR=str(out / "logs"), PYTHONIOENCODING="utf-8", FAKE_MODEL=MODEL,
                   FAKE_OLLAMA_LOG=str(out / "ollama_calls.json"), FAKE_INSIGHTS=INSIGHTS,
                   FAKE_POSITIONING=POSITIONING)
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
    return {"out": out, "calls": calls, "rows": rows, "servers": [s.base_url for s in servers]}


def _facts(prompt):
    return dict(line[2:].split(": ", 1) for line in prompt.splitlines() if line.startswith("- ") and ": " in line)


def test_the_model_is_asked_once_per_question_for_the_store_that_was_read(ai_run):
    # two calls (insights, positioning) for the Shopify store; none for the blocked store
    assert len(ai_run["calls"]) == 2
    assert all(c["model"] == MODEL for c in ai_run["calls"])
    ok_host = ai_run["servers"][0].split("//")[1]
    assert sum(ok_host in c["messages"][-1]["content"] for c in ai_run["calls"]) == 1  # the insight prompt
    assert all(ai_run["servers"][1].split("//")[1] not in c["messages"][-1]["content"] for c in ai_run["calls"])


def test_insight_prompt_carries_only_fields_the_pipeline_produced(ai_run):
    prompt = next(c["messages"][-1]["content"] for c in ai_run["calls"] if "关键洞察" in c["messages"][-1]["content"])
    facts = _facts(prompt)
    assert set(facts) <= set(PROMPT_FIELDS), set(facts) - set(PROMPT_FIELDS)
    assert "N/A" not in prompt and "None" not in prompt
    row = next(r for r in ai_run["rows"].values() if r["status"] == "ok")
    # each value is the one the pipeline reported for the store (report.csv)
    assert facts["网站域名"] == row["domain"]
    assert facts["电商平台"] == row["platform"]
    assert facts["价格区间"] == f"${float(row['price_min']):g} - ${float(row['price_max']):g}"
    assert facts["免运费门槛"] == f"${float(row['free_shipping_threshold']):g}"
    assert facts["退货天数"] == f"{row['return_days']}天"
    assert facts["免费退货"] == {"True": "是", "False": "否"}[row["free_returns"]]
    assert facts["评论平台"] == row["review_platform"]
    assert facts["支付方式"] == row["payment_methods"].replace("; ", ", ")
    assert facts["邮件订阅"] == {"True": "是", "False": "否"}[row["has_email_capture"]]
    # a value the pipeline did not produce is left out, not filled in
    assert row["review_count"] == "" and "评论数量" not in facts


def test_positioning_prompt_quotes_the_page(ai_run):
    prompt = next(c["messages"][-1]["content"] for c in ai_run["calls"] if "关键洞察" not in c["messages"][-1]["content"])
    row = next(r for r in ai_run["rows"].values() if r["status"] == "ok")
    assert row["brand_positioning"] in prompt
    assert "N/A" not in prompt and "None" not in prompt


def test_report_prints_the_response_in_the_ai_sections_of_that_store(ai_run):
    md = (ai_run["out"] / "report.md").read_text(encoding="utf-8")
    ok_host, blocked_host = (u.split("//")[1] for u in ai_run["servers"])
    blocked_at = md.index(f"## 🏪 {blocked_host}")
    ok_section = md[md.index(f"## 🏪 {ok_host}"):blocked_at]
    insights = ok_section.index("Key Insights (AI)")
    actions = ok_section.index("Actionable Recommendations (AI)")
    brand = ok_section.index("Brand Positioning Analysis (AI)")
    assert insights < ok_section.index("FAKE-INSIGHT-ONE") < ok_section.index("FAKE-INSIGHT-TWO") < actions
    assert actions < ok_section.index("FAKE-ACTION-ONE") < brand < ok_section.index(POSITIONING)
    assert "Ollama" in ok_section and MODEL in ok_section
    # nothing from the model in the blocked store's section
    assert "FAKE-" not in md[blocked_at:]


def test_business_report_names_the_model(ai_run):
    biz = (ai_run["out"] / "business_report.md").read_text(encoding="utf-8")
    assert MODEL in biz and "Ollama" in biz
