"""
Rebuild the reports from a stored scan with the --ai step, without fetching anything.

    python scripts/ai_from_snapshot.py --db output/demo-video/run/data/intel_cache.db \
        --ai-provider deepseek --lang en --outdir <dir>

Loads the newest snapshot of every store in the database (the one a run of main.py stored), runs
the AI step on it with the given provider, and writes report.md, report.csv and business_report.md
to <dir> (the business report is dated with the scan, as make_demo_video.py --reuse-run does). It
also writes <dir>/ai_run.json: per store the scan time, the facts the prompt listed, and the call's
run-log record (provider, model, tokens, cache-hit tokens, latency, error_type). The prompt text
and the API key are never written. A DeepSeek key is read as main.py reads it (DEEPSEEK_API_KEY in
the environment, else .env).
"""

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def rebuild(db, outdir, lang, analyzer) -> dict:
    """Run analyzer on the newest snapshot of each store in db; write the reports and ai_run.json."""
    from modules.ai_analyzer import prompt_facts
    from modules.business_report import BusinessReportGenerator
    from modules.models import SiteIntelligence
    from modules.report_writer import ReportWriter
    from modules.snapshot_store import SnapshotStore

    store = SnapshotStore(str(db))
    history = store.get_all_domains_history()
    sites = sorted((SiteIntelligence.from_dict(store.get_latest_snapshot(d)) for d in history),
                   key=lambda i: i.scan_timestamp)
    if not sites:
        raise SystemExit(f"{db} holds no snapshot")
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    summary = {"provider": analyzer.provider.name, "model": analyzer.model, "language": lang, "sites": []}
    for intel in sites:
        record = {"domain": intel.domain, "scan_timestamp": intel.scan_timestamp.isoformat(),
                  "status": intel.status}
        if intel.is_analyzed:
            data = intel.to_dict()
            intel.ai_analysis = analyzer.analyze_site(data)
            record.update(facts=prompt_facts(data), ai_call=analyzer.client.last_call,
                          error=intel.ai_analysis.get("error"))
        summary["sites"].append(record)
    run_info = {"ignore_robots": False, "render_js": False, "ai_requested": True, "ai_available": True,
                "ai_provider": analyzer.provider.name, "ai_model": analyzer.model}
    ReportWriter(str(outdir), language=lang).write_full_report(sites, {}, "report")
    BusinessReportGenerator(str(outdir), language=lang).generate_report(
        sites, {}, history, "business_report", run_info=run_info, report_date=sites[-1].scan_timestamp)
    (outdir / "ai_run.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return json.loads((outdir / "ai_run.json").read_text(encoding="utf-8"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0].strip())
    parser.add_argument("--db", required=True, help="SQLite file a run of main.py stored its scans in")
    parser.add_argument("--outdir", required=True)
    parser.add_argument("--ai-provider", required=True, choices=["ollama", "deepseek"])
    parser.add_argument("--ai-model", default=None)
    parser.add_argument("--lang", default="en", choices=["en", "zh"])
    args = parser.parse_args(argv)

    from modules import obs
    from modules.ai_analyzer import AIAnalyzer, AIConfig, make_provider
    if not Path(args.db).is_file():
        print(f"no database at {args.db}", file=sys.stderr)
        return 1
    try:
        provider = make_provider(args.ai_provider, args.ai_model)
    except ValueError as e:
        obs.swallowed("ai_from_snapshot.py:main", error_type="input_invalid", fallback="exit 1", stage="load")
        print(e, file=sys.stderr)
        return 1
    obs.init_run(log_dir=str(Path(args.outdir) / "logs"))
    try:
        analyzer = AIAnalyzer(AIConfig(provider=provider.name, model=provider.model, language=args.lang),
                              provider=provider)
        summary = rebuild(args.db, args.outdir, args.lang, analyzer)
    finally:
        obs.close_run()
    for site in summary["sites"]:
        call = site.get("ai_call") or {}
        print(f"{site['domain']} (scanned {site['scan_timestamp'][:16]}): {call.get('event', 'not run')}"
              f"{' ' + str(call['error_type']) if call.get('error_type') else ''}, "
              f"prompt {call.get('prompt_tokens')} tokens (cache hit {call.get('prompt_cache_hit_tokens')}), "
              f"completion {call.get('completion_tokens')}, {call.get('latency_ms')} ms")
    print(f"reports in {args.outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
