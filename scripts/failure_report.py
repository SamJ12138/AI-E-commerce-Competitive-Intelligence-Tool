#!/usr/bin/env python3
"""
failure_report.py - Summarise obs run logs (logs/run_*.jsonl). Standard library only.

Usage:
    python scripts/failure_report.py                 # newest log in logs/
    python scripts/failure_report.py LOG [LOG ...]   # specific files (or directories)
    python scripts/failure_report.py --all           # every log in logs/
    python scripts/failure_report.py LOG --out report.md

Sections:
  1. Pipeline failures: stage x error_type for fail events, excluding swallowed
     exceptions and silent fallbacks (those are section 2).
  2. Swallowed exceptions and silent fallbacks: stage x error_type, plus the
     code locations ("where") that fired most.
  3. Skips: stages that did not run, with the reason.
  4. Per-stage latency: count, p50, p95 and max of duration_ms.
  5. Fetches: which branch served each fetch, and status codes.
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ERROR_TYPES = ["input_invalid", "http", "blocked", "parse", "timeout", "external_api", "auth", "rate_limit",
               "unknown"]


def load_events(paths):
    events = []
    for path in paths:
        with open(path, encoding="utf-8") as f:
            for n, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    print(f"warning: {path}:{n}: not JSON ({exc})", file=sys.stderr)
    return events


def percentile(values, pct):
    """Nearest-rank percentile (pct in 0..100) of a non-empty list."""
    ordered = sorted(values)
    rank = max(1, -(-len(ordered) * pct // 100))  # ceil
    return ordered[int(rank) - 1]


def table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(out)


def crosstab(events):
    counts = defaultdict(Counter)
    for e in events:
        counts[e["stage"]][e.get("error_type") or "unknown"] += 1
    used = [t for t in ERROR_TYPES if any(c[t] for c in counts.values())]
    rows = []
    for stage in sorted(counts):
        c = counts[stage]
        rows.append([stage] + [c[t] or "" for t in used] + [sum(c.values())])
    totals = ["**total**"] + [sum(counts[s][t] for s in counts) or "" for t in used] + \
             [sum(sum(c.values()) for c in counts.values())]
    return table(["stage"] + used + ["total"], rows + [totals]) if rows else "_none_"


def build_report(events, sources):
    runs = sorted({e.get("run_id") for e in events if e.get("run_id")})
    sites = sorted({e.get("site") for e in events if e.get("site")})
    lines = ["# Failure report", "",
             f"Logs: {', '.join(str(s) for s in sources)}", "",
             f"Runs: {len(runs)} ({', '.join(runs)}) | sites: {len(sites)} | events: {len(events)}", ""]

    is_quiet = lambda e: e["context"].get("swallowed") or e["context"].get("degraded")
    fails = [e for e in events if e["event"] == "fail" and not is_quiet(e)]
    quiet = [e for e in events if is_quiet(e)]
    skips = [e for e in events if e["event"] == "skip" and not is_quiet(e)]

    lines += ["## 1. Pipeline failures (stage x error_type)", "", crosstab(fails), "",
              "`fetch` counts every HTTP call that returned an error; `products` / `policies` count the "
              "same failed page fetches again at page level (one row per page the pipeline wanted).", ""]

    lines += ["## 2. Swallowed exceptions and silent fallbacks (stage x error_type)", "",
              crosstab(quiet), ""]
    where = Counter((e["context"].get("where"), e.get("error_type"),
                     (e.get("error_message") or "")[:90], e["context"].get("fallback", "")) for e in quiet)
    if where:
        lines += ["Most frequent locations:", "",
                  table(["count", "where", "error_type", "message (truncated)", "fallback"],
                        [[n, w, t, m.replace("|", "/"), f.replace("|", "/")]
                         for (w, t, m, f), n in where.most_common(25)]), ""]

    lines += ["## 3. Skipped stages", ""]
    skip_counts = Counter((e["stage"], e["context"].get("kind") or "", (e.get("error_message") or
                          e["context"].get("reason") or "")[:100]) for e in skips)
    lines += [table(["count", "stage", "kind", "reason"],
                    [[n, s, k, r.replace("|", "/")] for (s, k, r), n in skip_counts.most_common()])
              if skip_counts else "_none_", ""]

    lines += ["## 4. Per-stage latency (ms, events with a duration)", ""]
    durations = defaultdict(list)
    for e in events:
        if e.get("duration_ms") is not None and e["event"] in ("success", "fail"):
            durations[e["stage"]].append(e["duration_ms"])
    rows = [[stage, len(v), f"{percentile(v, 50):.1f}", f"{percentile(v, 95):.1f}", f"{max(v):.1f}",
             f"{sum(v) / 1000:.1f}"] for stage, v in sorted(durations.items())]
    lines += [table(["stage", "n", "p50", "p95", "max", "total s"], rows) if rows else "_none_", ""]
    lines += ["`fetch` durations include the per-domain rate-limit wait (`rate_limit_wait_ms`); "
              "pipeline stages include the fetches they trigger.", ""]

    fetches = [e for e in events if e["stage"] == "fetch" and "served_by" in e["context"]]
    if fetches:
        lines += ["## 5. Fetches", ""]
        served = Counter((e["context"]["served_by"], e["context"].get("status"), e["event"]) for e in fetches)
        lines += [table(["served_by", "status", "event", "count"],
                        [[b, s, ev, n] for (b, s, ev), n in sorted(served.items(), key=lambda x: -x[1])]), ""]
        chains = Counter(" -> ".join(f"{a['branch']}({a['status']})" for a in e["context"].get("chain", []))
                         for e in fetches)
        lines += ["Branch chains:", "", table(["chain", "count"], [[c, n] for c, n in chains.most_common()]), ""]
        wait = sum(e["context"].get("rate_limit_wait_ms") or 0 for e in fetches) / 1000
        lines += [f"Total rate-limit wait across fetches: {wait:.1f} s", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("logs", nargs="*", help="log files or directories (default: newest in logs/)")
    parser.add_argument("--all", action="store_true", help="use every log in logs/")
    parser.add_argument("--out", help="write the Markdown report here as well")
    args = parser.parse_args(argv)

    paths = []
    for item in args.logs:
        p = Path(item)
        paths += sorted(p.glob("run_*.jsonl")) if p.is_dir() else [p]
    if not paths:
        candidates = sorted(Path("logs").glob("run_*.jsonl"), key=lambda p: p.stat().st_mtime)
        if not candidates:
            parser.error("no logs given and none found in logs/")
        paths = candidates if args.all else candidates[-1:]

    report = build_report(load_events(paths), paths)
    if args.out:
        Path(args.out).write_text(report + "\n", encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
