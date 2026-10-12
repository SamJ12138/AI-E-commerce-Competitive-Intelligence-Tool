#!/usr/bin/env python3
"""
demo.py - Run the tool on the three bundled fixture stores. Nothing leaves the machine.

The stores in tests/fixtures/stores are served on 127.0.0.1 (a Shopify-style store, a
WooCommerce-style store, and one that answers every request with a 403 challenge page), then
main.py runs once on all three and writes the reports.

Usage:
    python scripts/demo.py                    # English reports in output/demo/
    python scripts/demo.py --lang zh          # Chinese reports
    python scripts/demo.py --out some/dir     # somewhere else

Ports 8701-8703 are used when free (so the sample reports keep the same URLs); --port 0 picks free
ports. Each run starts with an empty scan history, so change detection has nothing to compare.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tests" / "fixtures" / "stores"))

from server import StoreServer  # noqa: E402

STORES = (
    ("shopify_basic", "a Shopify-style store"),
    ("woocommerce_promo", "a WooCommerce-style store with a sale"),
    ("blocked", "a store that answers every request with a 403 challenge page"),
)
REPORTS = ("report.md", "report.csv", "business_report.md")


def start(store, port):
    if port:
        try:
            return StoreServer(store, port=port).start()
        except OSError:
            pass  # port taken: any free one
    return StoreServer(store).start()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lang", choices=["en", "zh"], default="en", help="report language (default en)")
    parser.add_argument("--out", default=str(REPO / "output" / "demo"), help="output directory")
    parser.add_argument("--port", type=int, default=8701, help="first port to try (0: any free port)")
    args = parser.parse_args(argv)

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    db = out / "demo.db"
    if db.exists():
        db.unlink()

    servers = []
    try:
        for i, (store, _) in enumerate(STORES):
            servers.append(start(store, args.port + i if args.port else 0))
        sites = out / "sites.txt"
        sites.write_text("".join(f"# {what}\n{srv.base_url}\n" for srv, (_, what) in zip(servers, STORES)),
                         encoding="utf-8")
        config = out / "demo-config.yaml"
        config.write_text(
            "# Written by scripts/demo.py. The stores are local, so no delay between requests.\n"
            f"rate_limit_delay: 0\ndb_path: {db.as_posix()}\n", encoding="utf-8")
        for srv, (store, what) in zip(servers, STORES):
            print(f"serving {store} ({what}) at {srv.base_url}", flush=True)
        print(flush=True)
        cmd = [sys.executable, "main.py", "--sites", str(sites), "--outdir", str(out),
               "--config", str(config), "--lang", args.lang]
        env = dict(os.environ, ECI_LOG_DIR=str(out / "logs"))
        code = subprocess.run(cmd, cwd=REPO, env=env).returncode
    finally:
        for srv in servers:
            srv.stop()

    if code == 0:
        print("\nReports:")
        for name in REPORTS:
            print(f"  {out / name}")
        print(f"Run log: {out / 'logs'}")
    return code


if __name__ == "__main__":
    sys.exit(main())
