"""scripts/demo.py runs the tool on the bundled fixture stores; the README points only at things
that exist."""

import csv
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
REPORTS = ("report.md", "report.csv", "business_report.md")


@pytest.fixture(scope="module")
def demo_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("demo")
    proc = subprocess.run([sys.executable, "scripts/demo.py", "--out", str(out), "--port", "0", "--lang", "en"],
                          cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=600, env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
    return proc, out


def test_demo_writes_the_three_reports(demo_run):
    proc, out = demo_run
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    for name in REPORTS:
        assert (out / name).is_file(), name
    rows = list(csv.DictReader(open(out / "report.csv", encoding="utf-8-sig")))
    assert sorted(r["status"] for r in rows) == ["blocked", "ok", "ok"]
    assert {r["platform"] for r in rows if r["status"] == "ok"} == {"Shopify", "WooCommerce"}


def test_demo_says_where_the_reports_are(demo_run):
    proc, out = demo_run
    for name in REPORTS:
        assert name in proc.stdout


def test_committed_sample_comes_from_the_demo():
    for sub in ("", "zh"):
        for name in REPORTS:
            assert (REPO / "docs" / "sample" / sub / name).is_file(), f"{sub}/{name}"
    md = (REPO / "docs" / "sample" / "report.md").read_text(encoding="utf-8")
    assert "Northfield Goods" in md and "blocked automated access" in md


def _readme():
    return (REPO / "README.md").read_text(encoding="utf-8")


def test_readme_links_resolve():
    links = re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", _readme())
    local = [l for l in links if not re.match(r"[a-z]+://", l)]
    assert local, "README has no relative links"
    missing = [l for l in local if not (REPO / l).exists()]
    assert not missing, missing


def test_readme_flags_exist():
    import main
    known = {opt for p in main.main.params for opt in p.opts}
    used = set(re.findall(r"(?<![\w-])(--[a-z][a-z-]+)", _readme()))
    pip_or_other = {"--upgrade", "--version"}
    assert not (used - known - pip_or_other), sorted(used - known - pip_or_other)


def test_readme_quickstart_runs_the_demo():
    text = _readme()
    assert "python scripts/demo.py" in text
    assert "pip install -r requirements.txt" in text


@pytest.mark.parametrize("encoding", ["ascii", "gbk", "cp1252"])
def test_main_runs_when_the_console_cannot_print_every_character(tmp_path, encoding):
    # A Windows console on a legacy code page (or output piped there) cannot encode the emoji in
    # the console output; that used to end the run with UnicodeEncodeError before any fetch.
    sys.path.insert(0, str(REPO / "tests" / "fixtures" / "stores"))
    from server import StoreServer
    with StoreServer("shopify_basic") as srv:
        (tmp_path / "sites.txt").write_text(srv.base_url + "\n", encoding="utf-8")
        (tmp_path / "c.yaml").write_text(f"rate_limit_delay: 0\ndb_path: {(tmp_path / 'x.db').as_posix()}\n",
                                         encoding="utf-8")
        env = {k: v for k, v in __import__("os").environ.items() if k != "PYTHONUTF8"}
        env.update(PYTHONIOENCODING=encoding, ECI_LOG_DIR=str(tmp_path))
        proc = subprocess.run([sys.executable, "main.py", "--sites", str(tmp_path / "sites.txt"),
                               "--outdir", str(tmp_path), "--config", str(tmp_path / "c.yaml"), "--lang", "zh"],
                              cwd=REPO, capture_output=True, env=env, timeout=300)
    assert proc.returncode == 0, proc.stderr.decode(encoding, "replace")[-1500:]
    assert (tmp_path / "report.csv").is_file()
