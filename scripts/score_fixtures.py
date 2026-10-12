#!/usr/bin/env python3
"""
score_fixtures.py - Run main.py against the local fixture stores and score report.csv
against each store's fixtures.json, field by field.

Every store is served on 127.0.0.1 by tests/fixtures/stores/server.py; nothing
leaves the machine. Each run gets its own output directory, SQLite file and
obs log, so runs never share snapshot history.

Usage:
    python scripts/score_fixtures.py                       # all runs, print Markdown
    python scripts/score_fixtures.py --skip-browser        # no --render-js run
    python scripts/score_fixtures.py --baseline-dir docs/baseline
        # also writes fixture_scores.md / .json, failure_report.md and copies the logs

Runs:
    shopify_basic        main.py --lang en
    woocommerce_promo    main.py --lang en
    blocked              main.py --lang en               (requests -> cloudscraper)
    blocked_render_js    main.py --lang en --render-js   (browser -> cloudscraper)

Verdicts: match / partial / mismatch. An expected value of null means "the
tool cannot know this"; a definite answer (False, "USD", a number) is a
mismatch, an empty answer is a match.
"""

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tests" / "fixtures" / "stores"))
sys.path.insert(0, str(REPO / "scripts"))

from server import StoreServer, load_ground_truth  # noqa: E402
import failure_report  # noqa: E402

RUNS = [
    ("shopify_basic", "shopify_basic", []),
    ("woocommerce_promo", "woocommerce_promo", []),
    ("blocked", "blocked", []),
    ("blocked_render_js", "blocked", ["--render-js"]),
]

# (score name, report.csv column, obs field name, kind)
FIELDS = [
    ("platform", "platform", "platform", "platform"),
    ("price_min", "price_min", "price_min", "number"),
    ("price_max", "price_max", "price_max", "number"),
    ("price_median", "price_median", "price_median", "number"),
    ("currency", "currency", "currency", "text"),
    ("has_discounts", "has_discounts", "has_discounts", "bool"),
    ("free_shipping_threshold", "free_shipping_threshold", "free_shipping_threshold", "number"),
    ("return_days", "return_days", "return_days", "number"),
    ("free_returns", "free_returns", "free_returns", "bool"),
    ("payment_methods", "payment_methods", "payment_methods", "set"),
    ("review_platform", "review_platform", "review_platform", "text"),
    ("has_email_capture", "has_email_capture", "has_email_capture", "bool"),
    ("has_popup", "has_popup", "has_popup", "bool"),
    ("has_loyalty", "has_loyalty", "has_loyalty", "bool"),
    ("has_referral", "has_referral", "has_referral", "bool"),
    ("pixels", "pixels_detected", "pixels_detected", "set"),
    ("announcement_bar", "announcement_bar", "announcement_bar", "text"),
]

CARD_BRANDS = {"Visa", "Mastercard", "American Express", "Discover"}
UNKNOWN_PLATFORM = "Custom/Unknown"
CJK = re.compile(r"[一-鿿]")


def parse_cell(value, kind):
    if value is None or value == "":
        return [] if kind == "set" else None
    if kind == "bool":
        return {"True": True, "False": False}.get(value, value)
    if kind == "number":
        try:
            return float(value)
        except ValueError:
            return value
    if kind == "set":
        return sorted(v.strip() for v in value.split(";") if v.strip())
    return value


def verdict(expected, got, kind):
    """Return (verdict, note)."""
    if expected is None:
        if got in (None, "", []) or (kind == "platform" and got == UNKNOWN_PLATFORM):
            return "match", ""
        return "mismatch", "definite value for data the tool could not have seen"
    if kind == "number":
        ok = isinstance(got, float) and abs(got - float(expected)) < 0.005
        return ("match" if ok else "mismatch"), ""
    if kind == "set":
        exp, got_set = set(expected), set(got or [])
        if exp == got_set:
            return "match", ""
        collapsed = {("Credit Card" if v in CARD_BRANDS else v) for v in exp}
        if collapsed == got_set:
            return "partial", "card brands reported only as generic 'Credit Card'"
        if exp & got_set:
            return "partial", f"missing {sorted(exp - got_set)}, extra {sorted(got_set - exp)}"
        return "mismatch", ""
    return ("match" if got == expected else "mismatch"), ""


def read_log(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def field_sources(events, site):
    out = {}
    for e in events:
        c = e["context"]
        if c.get("kind") == "field" and e.get("site") == site:
            out[c["field"]] = c
    return out


GUESSED_ORIGINS = ("guessed_priority_path", "guessed_platform_path")


def priority_404s(events, site):
    """Guessed paths from the discovery page list, and what each fetch returned."""
    guessed = []
    for e in events:
        c = e["context"]
        if e.get("site") == site and c.get("kind") == "page_list":
            guessed = [p["url"] for p in c["pages"] if p.get("origin") in GUESSED_ORIGINS]
    fetched = {}
    for e in events:
        c = e["context"]
        if e.get("site") == site and e["stage"] == "fetch" and "served_by" in c and c["url"] in guessed:
            fetched.setdefault(c["url"], []).append(e)
    return [{"url": url,
             "statuses": [e["context"]["status"] for e in fetched.get(url, [])],
             "fetch_ms": round(sum(e["duration_ms"] or 0 for e in fetched.get(url, [])), 1)}
            for url in guessed]


def scrub_paths(text, replacements):
    """Replace local directories (native, POSIX and JSON-escaped spellings) with placeholders."""
    for directory, placeholder in sorted(replacements.items(), key=lambda kv: -len(str(kv[0]))):
        native = str(Path(directory).resolve())
        for spelling in {native, Path(native).as_posix(), json.dumps(native)[1:-1]}:
            text = text.replace(spelling, placeholder)
    return text


def run_one(label, store, extra_args, out_root, python, config_extra=None):
    """Run main.py on one fixture store. config_extra: more config.yaml keys (e.g. rate_limit_delay)."""
    out_dir = out_root / label
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    run_id = f"{label}-{time.strftime('%Y%m%dT%H%M%S')}"
    with StoreServer(store) as srv:
        site = srv.base_url
        (out_dir / "sites.txt").write_text(site + "\n", encoding="utf-8")
        config_lines = [f"db_path: {(out_dir / 'intel.db').as_posix()}"]
        config_lines += [f"{key}: {value}" for key, value in (config_extra or {}).items()]
        (out_dir / "config.yaml").write_text("\n".join(config_lines) + "\n", encoding="utf-8")
        cmd = [python, "main.py", "--sites", str(out_dir / "sites.txt"), "--outdir", str(out_dir),
               "--config", str(out_dir / "config.yaml"), "--lang", "en"] + extra_args
        env = dict(__import__("os").environ, ECI_LOG_DIR=str(out_dir), ECI_RUN_ID=run_id,
                   PYTHONIOENCODING="utf-8", COLUMNS="200")
        started = time.time()
        proc = subprocess.run(cmd, cwd=REPO, env=env, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=900)
        wall = time.time() - started
        requests_seen = srv.request_log()
    (out_dir / "stdout.txt").write_text(proc.stdout + "\n--- stderr ---\n" + proc.stderr, encoding="utf-8")
    (out_dir / "requests.json").write_text(json.dumps(requests_seen, indent=1), encoding="utf-8")
    log_path = out_dir / f"run_{run_id}.jsonl"
    return {"label": label, "store": store, "args": extra_args, "site": site, "out_dir": out_dir,
            "exit_code": proc.returncode, "wall_s": round(wall, 1), "log": log_path,
            "requests": requests_seen}


def score_run(run):
    truth = load_ground_truth(run["store"])
    expected = truth["expected"]
    out_dir, site = run["out_dir"], run["site"]
    events = read_log(run["log"]) if run["log"].exists() else []
    sources = field_sources(events, site)

    csv_path = out_dir / "report.csv"
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8-sig"))) if csv_path.exists() else []
    row = rows[0] if rows else {}

    scored = []
    for name, column, obs_name, kind in FIELDS:
        exp = expected.get(name)
        if kind == "set" and exp is not None:
            exp = sorted(exp)
        got = parse_cell(row.get(column), "set" if kind == "set" else ("text" if kind == "platform" else kind))
        v, note = verdict(exp, got, kind)
        src = sources.get(obs_name, {})
        scored.append({"field": name, "expected": exp, "got": got, "verdict": v, "note": note,
                       "source": src.get("source"), "detail": src.get("detail"), "source_url": src.get("url")})

    statuses = {}
    for r in run["requests"]:
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1
    guessed = priority_404s(events, site)
    guessed_404 = [g for g in guessed if 404 in g["statuses"]]

    checks = {"csv_rows": len(rows), "status": row.get("status"),
              "expected_status": truth.get("status"), "fetch_attempts": row.get("fetch_attempts")}
    bp = row.get("brand_positioning", "")
    checks["brand_positioning"] = bp
    checks["brand_positioning_is_chinese_under_lang_en"] = bool(CJK.search(bp or ""))
    business = out_dir / "business_report.md"
    if business.exists():
        text = business.read_text(encoding="utf-8")
        m = re.search(r"\*\*(?:Sites|Competitors) Analyzed:\*\* (\d+)", text)
        checks["business_competitors_analyzed"] = int(m.group(1)) if m else None
        checks["business_says_multiple_players"] = "Multiple players in similar price ranges" in text
        checks["business_says_shopify_reliance"] = "Heavy reliance on Shopify ecosystem" in text
        checks["business_claims_qwen_analysis"] = "AI-powered insight generation using Qwen2.5" in text
        checks["business_claims_robots_respected"] = ("respecting robots.txt" in text
                                                      or "robots.txt was respected" in text)
        checks["business_mentions_competitors"] = bool(re.search(r"competitor", text, re.I))
        method = text.split("### Methodology", 1)[1].split("###", 1)[0] if "### Methodology" in text else ""
        checks["business_methodology"] = " / ".join(
            line.strip("- ").strip() for line in method.splitlines() if line.strip().startswith("- "))
    report_md = out_dir / "report.md"
    if report_md.exists():
        md = report_md.read_text(encoding="utf-8")
        insights = md.split("### 🔍", 1)[1].split("###", 1)[0] if "### 🔍" in md else ""
        checks["report_md_insights_chinese_under_lang_en"] = bool(CJK.search(insights))

    fetches = [e for e in events if e["stage"] == "fetch" and "served_by" in e["context"]]
    chains = [{"url": e["context"]["url"], "event": e["event"], "status": e["context"]["status"],
               "served_by": e["context"]["served_by"], "bytes": e["context"]["bytes"],
               "error_type": e["error_type"],
               "chain": [f"{a['branch']}({a['status']}, {a['bytes']}B{', ' + a['error'] if a['error'] else ''})"
                         for a in e["context"]["chain"]]}
              for e in fetches]

    return {
        "label": run["label"], "store": run["store"], "args": run["args"], "exit_code": run["exit_code"],
        "wall_s": run["wall_s"], "site": site, "log": str(run["log"]),
        "requests_total": len(run["requests"]), "requests_by_status": statuses,
        "requests_404": statuses.get(404, 0),
        "guessed_priority_paths": len(guessed), "guessed_priority_404": len(guessed_404),
        "guessed_404_fetch_s": round(sum(g["fetch_ms"] for g in guessed_404) / 1000, 1),
        "guessed_404_paths": [g["url"].replace(site, "") for g in guessed_404],
        "fields": scored, "checks": checks, "fetches": chains,
        "summary": {v: sum(1 for f in scored if f["verdict"] == v) for v in ("match", "partial", "mismatch")},
    }


def fmt(value):
    if value is None:
        return "null"
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, list):
        return "[" + ", ".join(str(v) for v in value) + "]"
    return str(value)


def to_markdown(results):
    icon = {"match": "✅", "partial": "⚠️", "mismatch": "❌"}
    lines = ["# Fixture scores (baseline)", "",
             "Generated by `python scripts/score_fixtures.py`. Each run: one fixture store on 127.0.0.1, "
             "`main.py --lang en`, its own output directory, SQLite file and obs log. "
             "`source` is the obs `field` event for that value: the rule that produced it.", ""]
    lines += ["| run | exit | wall s | status | match | partial | mismatch | requests (by status) | 404s | "
              "guessed paths | of which 404 | time in those 404 fetches |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        s = r["summary"]
        lines.append(f"| {r['label']} | {r['exit_code']} | {r['wall_s']} | {r['checks'].get('status')} | "
                     f"{s['match']} | {s['partial']} | "
                     f"{s['mismatch']} | {r['requests_total']} {r['requests_by_status']} | {r['requests_404']} | "
                     f"{r['guessed_priority_paths']} | {r['guessed_priority_404']} | {r['guessed_404_fetch_s']} s |")
    lines.append("")
    for r in results:
        lines += [f"## {r['label']}", "", f"`main.py --lang en {' '.join(r['args'])}`".replace("  ", " ") +
                  f" against {r['store']} ({r['site']}); log `{Path(r['log']).name}`", "",
                  "| field | expected | got | verdict | source (obs) |", "|---|---|---|---|---|"]
        for f in r["fields"]:
            src = f"{f['source']}: {f['detail']}" if f["source"] else "(no field event)"
            src = src.replace("|", "/").replace("\n", " ")
            if len(src) > 220:
                src = src[:217] + "..."
            note = f" ({f['note']})" if f["note"] else ""
            lines.append(f"| {f['field']} | {fmt(f['expected'])} | {fmt(f['got'])} | "
                         f"{icon[f['verdict']]} {f['verdict']}{note} | {src} |")
        lines += ["", "Report-level checks:", ""]
        for k, v in r["checks"].items():
            lines.append(f"- `{k}`: {fmt(v)}")
        if r["guessed_404_paths"]:
            lines += ["", f"Guessed paths that 404'd ({r['guessed_priority_404']}): " +
                      ", ".join(f"`{p}`" for p in r["guessed_404_paths"])]
        if r["store"] == "blocked":
            lines += ["", "Fetches (branch chain):", ""]
            for fch in r["fetches"]:
                lines.append(f"- {fch['url'].replace(r['site'], '') or '/'}: {fch['event']} "
                             f"served_by={fch['served_by']} status={fch['status']} "
                             f"error_type={fch['error_type']} chain: {' -> '.join(fch['chain'])}")
        lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skip-browser", action="store_true", help="skip the --render-js run")
    parser.add_argument("--runs", nargs="*", help="labels to run (default: all)")
    parser.add_argument("--out-root", default=str(REPO / "output" / "fixture_runs"))
    parser.add_argument("--baseline-dir", help="write fixture_scores.md/.json, failure_report.md and logs here")
    args = parser.parse_args(argv)

    python = sys.executable
    out_root = Path(args.out_root)
    selected = [r for r in RUNS if (not args.runs or r[0] in args.runs)
                and not (args.skip_browser and "--render-js" in r[2])]
    results = []
    for label, store, extra in selected:
        print(f"running {label} ...", file=sys.stderr, flush=True)
        run = run_one(label, store, extra, out_root, python)
        results.append(score_run(run))

    md = to_markdown(results)
    sys.stdout.reconfigure(encoding="utf-8")
    print(md)
    if args.baseline_dir:
        base = Path(args.baseline_dir).resolve()
        (base / "logs").mkdir(parents=True, exist_ok=True)
        logs = []
        for r in results:
            src = Path(r["log"])
            if src.exists():
                dst = base / "logs" / src.name
                dst.write_text(scrub_paths(src.read_text(encoding="utf-8"),
                                           {out_root: "<out>", REPO: "<repo>"}), encoding="utf-8")
                logs.append(dst)
                r["log"] = dst.relative_to(REPO).as_posix()
        (base / "fixture_scores.md").write_text(to_markdown(results) + "\n", encoding="utf-8")
        (base / "fixture_scores.json").write_text(json.dumps(results, indent=1, ensure_ascii=False, default=str) + "\n",
                                                  encoding="utf-8")
        report = failure_report.build_report(failure_report.load_events(logs),
                                             [p.relative_to(REPO).as_posix() for p in logs])
        (base / "failure_report.md").write_text(report + "\n", encoding="utf-8")
        print(f"wrote {base}", file=sys.stderr)


if __name__ == "__main__":
    main()
