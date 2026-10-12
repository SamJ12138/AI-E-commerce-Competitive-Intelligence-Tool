"""
real_corpus.py - Run main.py on the real-store corpus and score it against docs/real-corpus/<store>.json.

Ground truth was written by hand from the stores' pages (facts and source URLs only; no page HTML is
kept in the repo). This script touches real sites only in `run`, once per store.

Usage:
    python scripts/real_corpus.py run --out-root <dir> [--stores a b ...]
    python scripts/real_corpus.py score --out-root <dir> [--md docs/real-corpus/scores.md] [--label baseline]

run: one main.py process per store, default settings (`--lang en`, default rate limit, max pages and
max products, robots.txt respected, no --render-js, no --ignore-robots), its own output directory,
SQLite file and obs log. One deviation from the defaults: the cloudscraper fallback branch is
switched off (`modules.http_client.CLOUDSCRAPER_AVAILABLE = False` in the launching process), because
real-site runs must not take the cloudscraper path. A 403 therefore ends on `requests 403`.
`--allow-cloudscraper` keeps the default chain.

score: per store and field, match / partial / mismatch / missing, and for every miss the obs log's
final `field` event (source, detail), the last candidate that produced a value (stage), and whether
the tool fetched the page the fact came from.
"""

import argparse
import csv
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parent.parent
TRUTH_DIR = REPO / "docs" / "real-corpus"

# ground-truth field -> (report.csv column, obs field name, kind)
FIELDS = {
    "platform": ("platform", "platform", "text"),
    "free_shipping_threshold": ("free_shipping_threshold", "free_shipping_threshold", "number"),
    "return_days": ("return_days", "return_days", "number"),
    "free_returns": ("free_returns", "free_returns", "bool"),
    "payment_methods": ("payment_methods", "payment_methods", "set"),
    "review_platform": ("review_platform", "review_platform", "text"),
    "has_loyalty": ("has_loyalty", "has_loyalty", "bool"),
    "has_email_capture": ("has_email_capture", "has_email_capture", "bool"),
    "has_popup": ("has_popup", "has_popup", "bool"),
}
ORDER = ["status", "platform", "products", "free_shipping_threshold", "return_days", "free_returns",
         "payment_methods", "review_platform", "has_loyalty", "has_email_capture", "has_popup"]
UNKNOWN_PLATFORM = "Custom/Unknown"

BOOTSTRAP = (
    "import sys, runpy\n"
    "import modules.http_client as h\n"
    "h.CLOUDSCRAPER_AVAILABLE = False\n"
    "sys.argv = ['main.py'] + sys.argv[1:]\n"
    "runpy.run_path('main.py', run_name='__main__')\n"
)


def load_truth(stores=None, truth_dir=None):
    out = {}
    for path in sorted(Path(truth_dir or TRUTH_DIR).glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if "fields" in data and (not stores or data["store"] in stores):
            out[data["store"]] = data
    return out


# ---------------------------------------------------------------- run

def run_store(store, truth, out_root, python, allow_cloudscraper):
    out_dir = out_root / store
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.iterdir():
        if old.is_file():
            old.unlink()
    run_id = f"{store}-{time.strftime('%Y%m%dT%H%M%S')}"
    (out_dir / "sites.txt").write_text(truth["url"] + "\n", encoding="utf-8")
    (out_dir / "config.yaml").write_text(f"db_path: {(out_dir / 'intel.db').as_posix()}\n", encoding="utf-8")
    args = ["--sites", str(out_dir / "sites.txt"), "--outdir", str(out_dir),
            "--config", str(out_dir / "config.yaml"), "--lang", "en"]
    cmd = [python, "main.py"] + args if allow_cloudscraper else [python, "-c", BOOTSTRAP] + args
    env = dict(os.environ, ECI_LOG_DIR=str(out_dir), ECI_RUN_ID=run_id, PYTHONIOENCODING="utf-8", COLUMNS="200")
    started = time.time()
    proc = subprocess.run(cmd, cwd=REPO, env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=1800)
    meta = {"store": store, "url": truth["url"], "run_id": run_id, "exit_code": proc.returncode,
            "wall_s": round(time.time() - started, 1), "cloudscraper": allow_cloudscraper,
            "started": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(started))}
    (out_dir / "stdout.txt").write_text(proc.stdout + "\n--- stderr ---\n" + proc.stderr, encoding="utf-8")
    (out_dir / "run.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return meta


# ---------------------------------------------------------------- score

def read_log(path):
    if not path or not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def norm_path(url):
    return (urlsplit(url).path.rstrip("/") or "/").lower()


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


def empty(v):
    return v is None or v == [] or v == ""


def verdict_value(exp, got, kind, accept=None):
    if kind == "text" and got == UNKNOWN_PLATFORM and exp != UNKNOWN_PLATFORM:
        got = None
    if empty(exp):
        if empty(got):
            return "match", ""
        return "mismatch", "definite value where the pages state none"
    if empty(got):
        return "missing", ""
    if kind == "number":
        options = [float(a) for a in (accept or [exp])]
        if isinstance(got, float) and any(abs(got - o) < 0.005 for o in options):
            return "match", ("one of the values the page states" if accept else "")
        return "mismatch", ""
    if kind == "set":
        e, g = set(exp), set(got)
        if e == g:
            return "match", ""
        if e & g:
            return "partial", f"missing {sorted(e - g)}, extra {sorted(g - e)}"
        return "mismatch", f"missing {sorted(e - g)}, extra {sorted(g - e)}"
    return ("match" if got == exp else "mismatch"), ""


def score_products(expected, tool_products):
    """Per ground-truth product: found by URL path, price (or within its range), compare-at."""
    by_path = {}
    for p in tool_products:
        by_path.setdefault(norm_path(p.get("url") or ""), []).append(p)
    rows = []
    for gt in expected:
        found = by_path.get(norm_path(gt["url"]), [])
        if not found:
            rows.append({"title": gt["title"], "verdict": "missing", "expected": gt["price"],
                         "expected_compare_at": gt.get("compare_at"), "got": None})
            continue
        price = (found[0].get("price") or {})
        cur, cmp_ = price.get("current_price"), price.get("compare_at_price")
        lo, hi = gt.get("price_range") or (gt["price"], gt["price"])
        price_ok = cur is not None and lo - 0.005 <= cur <= hi + 0.005
        exp_cmp = gt.get("compare_at")
        cmp_ok = (not exp_cmp and not cmp_) or (exp_cmp and cmp_ and abs(cmp_ - exp_cmp) < 0.005)
        verdict = "match" if price_ok and cmp_ok else "mismatch"
        rows.append({"title": gt["title"], "verdict": verdict, "expected": gt["price"],
                     "expected_range": gt.get("price_range"), "expected_compare_at": exp_cmp,
                     "got": cur, "got_compare_at": cmp_})
    verdicts = [r["verdict"] for r in rows]
    if not expected:
        overall = "match" if not tool_products else "mismatch"
        note = "" if not tool_products else f"{len(tool_products)} products reported on a site with none"
    elif all(v == "match" for v in verdicts):
        overall, note = "match", ""
    elif all(v == "missing" for v in verdicts):
        overall, note = "missing", ""
    elif "match" in verdicts:
        overall, note = "partial", f"{verdicts.count('match')} of {len(verdicts)} right"
    else:
        overall, note = "mismatch", ""
    return overall, note, rows


def obs_for_field(events, site, name):
    final, produced = None, None
    for e in events:
        c = e.get("context") or {}
        if e.get("site") != site or c.get("field") != name:
            continue
        if c.get("kind") == "field":
            final = c
        elif c.get("kind") == "candidate" and c.get("source") != "default" and not empty(c.get("value")):
            produced = {"stage": e.get("stage"), **c}
    return final, produced


def fetched_pages(events, site):
    pages = {}
    for e in events:
        c = e.get("context") or {}
        if e.get("site") == site and e.get("stage") == "fetch" and c.get("url"):
            pages[norm_path(c["url"])] = c.get("status")
    return pages


def score_store(store, truth, out_dir):
    meta = json.loads((out_dir / "run.json").read_text(encoding="utf-8")) if (out_dir / "run.json").exists() else {}
    log = next(iter(sorted(out_dir.glob("run_*.jsonl"))), None)
    events = read_log(log)
    rows = list(csv.DictReader(open(out_dir / "report.csv", encoding="utf-8-sig"))) if (out_dir / "report.csv").exists() else []
    row = rows[0] if rows else {}
    snap = {}
    if (out_dir / "intel.db").exists():
        con = sqlite3.connect(out_dir / "intel.db")
        got = con.execute("SELECT data FROM snapshots ORDER BY id DESC LIMIT 1").fetchone()
        con.close()
        snap = json.loads(got[0]) if got else {}
    site = truth["url"]
    sites_in_log = {e.get("site") for e in events if e.get("site")}
    if site not in sites_in_log and sites_in_log:
        site = sorted(sites_in_log)[0]
    pages = fetched_pages(events, site)
    requests_by_status = {}
    for status in pages.values():
        requests_by_status[str(status)] = requests_by_status.get(str(status), 0) + 1

    results = []
    status_got = row.get("status") or snap.get("status") or "(no row)"
    results.append({"field": "status", "expected": truth["status"], "got": status_got,
                    "verdict": "match" if status_got == truth["status"] else "mismatch", "note": ""})
    for name in ORDER[1:]:
        spec = truth["fields"][name]
        if name == "products":
            exp = spec["value"]
            if exp is None:
                tool = snap.get("all_products") or []
                v, note, detail = ("match", "", []) if not tool else ("mismatch", "products reported for a blocked site", [])
            else:
                v, note, detail = score_products(exp, snap.get("all_products") or [])
            results.append({"field": "products", "expected": exp, "got": len(snap.get("all_products") or []),
                            "verdict": v, "note": note, "products": detail, "source_url": spec["source"]})
            continue
        column, obs_name, kind = FIELDS[name]
        got = parse_cell(row.get(column), kind) if row else None
        exp = spec["value"]
        if kind == "set" and exp is not None:
            exp = sorted(exp)
        v, note = verdict_value(exp, got, kind, spec.get("accept"))
        r = {"field": name, "expected": exp, "got": got, "verdict": v, "note": note, "source_url": spec["source"]}
        if v != "match":
            final, produced = obs_for_field(events, site, obs_name)
            r["obs_final"] = {k: final.get(k) for k in ("source", "detail", "url")} if final else None
            r["obs_produced_by"] = ({k: produced.get(k) for k in ("stage", "source", "detail", "url")}
                                    if produced else None)
            r["source_page_fetched"] = pages.get(norm_path(spec["source"])) if spec["source"].startswith("http") else None
        results.append(r)
    counts = {k: sum(1 for r in results if r["verdict"] == k) for k in ("match", "partial", "mismatch", "missing")}
    return {"store": store, "url": truth["url"], "category": truth.get("category"), "run": meta,
            "status": status_got, "fetch_attempts": row.get("fetch_attempts", ""),
            "pages_fetched": len(pages), "requests_by_status": requests_by_status,
            "counts": counts, "fields": results}


def fmt(v):
    if isinstance(v, float):
        return f"{v:g}"
    if isinstance(v, list):
        return ", ".join(map(str, v)) if v else "[]"
    return "null" if v is None else str(v)


def render_md(scores, label):
    out = [f"# Real-store corpus scores ({label})", "",
           "Generated by `python scripts/real_corpus.py score`. Ground truth: `docs/real-corpus/<store>.json` "
           "(facts read by hand on 2026-10-12, with the URL each came from). Verdicts: match / partial / "
           "mismatch / missing (the tool gave no value where the store states one). `products` compares each "
           "ground-truth product's price and compare-at price with the product the tool reported at the same URL path.",
           "", "| store | status | fetch | pages | match | partial | mismatch | missing |", "|---|---|---|---|---|---|---|---|"]
    for s in scores:
        c = s["counts"]
        out.append(f"| {s['store']} | {s['status']} | {s['fetch_attempts'] or '-'} | {s['pages_fetched']} | "
                   f"{c['match']} | {c['partial']} | {c['mismatch']} | {c['missing']} |")
    out += ["", "## Per field", "", "| field | " + " | ".join(s["store"] for s in scores) + " |",
            "|---|" + "---|" * len(scores)]
    for name in ORDER:
        cells = []
        for s in scores:
            r = next(r for r in s["fields"] if r["field"] == name)
            cells.append(r["verdict"])
        out.append(f"| {name} | " + " | ".join(cells) + " |")
    for s in scores:
        out += ["", f"## {s['store']}", "", f"{s['url']} ({s['category']}); run {s['run'].get('run_id', '?')}, "
                f"exit {s['run'].get('exit_code', '?')}, {s['run'].get('wall_s', '?')} s, status {s['status']}, "
                f"pages fetched {s['pages_fetched']} {s['requests_by_status']}.", "",
                "| field | expected | got | verdict | note |", "|---|---|---|---|---|"]
        for r in s["fields"]:
            exp = r["expected"]
            if r["field"] == "products" and isinstance(exp, list):
                exp = f"{len(exp)} products"
            got = r["got"]
            if r["field"] == "products":
                got = f"{got} products reported"
            out.append(f"| {r['field']} | {fmt(exp)} | {fmt(got)} | {r['verdict']} | {r.get('note', '')} |")
        misses = [r for r in s["fields"] if r["verdict"] != "match"]
        if misses:
            out += ["", "Misses:", ""]
        for r in misses:
            if r["field"] == "products":
                for p in r.get("products", []):
                    if p["verdict"] != "match":
                        exp = fmt(p["expected"]) + (f" (range {fmt(p['expected_range'])})" if p.get("expected_range") else "")
                        out.append(f"- products / {p['title']}: {p['verdict']}; expected {exp}, compare-at "
                                   f"{fmt(p['expected_compare_at'])}; got {fmt(p['got'])}, compare-at "
                                   f"{fmt(p.get('got_compare_at'))}")
                if r.get("note"):
                    out.append(f"- products: {r['note']}")
                continue
            if r["field"] == "status":
                out.append(f"- status: expected {r['expected']}, got {r['got']}")
                continue
            final = r.get("obs_final") or {}
            produced = r.get("obs_produced_by")
            fetched = r.get("source_page_fetched")
            line = (f"- {r['field']}: expected {fmt(r['expected'])} (from {r['source_url']}), got {fmt(r['got'])}. "
                    f"obs final: source `{final.get('source')}`, {final.get('detail') or '-'}")
            if produced:
                line += f"; produced in stage `{produced['stage']}` by `{produced['source']}` on {produced.get('url')}: {produced.get('detail')}"
            else:
                line += "; no extractor produced a value"
            line += (f". Source page fetched by the tool: {'yes (' + str(fetched) + ')' if fetched else 'no'}.")
            out.append(line)
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--out-root", required=True)
    r.add_argument("--stores", nargs="*")
    r.add_argument("--allow-cloudscraper", action="store_true")
    s = sub.add_parser("score")
    s.add_argument("--out-root", required=True)
    s.add_argument("--stores", nargs="*")
    s.add_argument("--md")
    s.add_argument("--json")
    s.add_argument("--label", default="baseline")
    for p in (r, s):
        p.add_argument("--truth-dir", help="ground-truth directory (default docs/real-corpus)")
    a = ap.parse_args()
    out_root = Path(a.out_root)
    truth = load_truth(a.stores, a.truth_dir)
    if a.cmd == "run":
        out_root.mkdir(parents=True, exist_ok=True)
        for store, t in truth.items():
            print(f"running {store} ({t['url']}) ...", flush=True)
            meta = run_store(store, t, out_root, sys.executable, a.allow_cloudscraper)
            print(f"  exit {meta['exit_code']}, {meta['wall_s']} s", flush=True)
        return
    scores = [score_store(store, t, out_root / store) for store, t in truth.items()]
    md = render_md(scores, a.label)
    if a.md:
        Path(a.md).write_text(md, encoding="utf-8")
    if a.json:
        Path(a.json).write_text(json.dumps(scores, indent=1, ensure_ascii=False), encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(md)


if __name__ == "__main__":
    main()
