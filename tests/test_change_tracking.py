"""Batch 6: snapshot identity includes the port; a change is reported on the scan that saw it.

main.main runs in-process (click CliRunner) with --monitor against fixture stores whose
servers stay up across scans, so each store keeps its port (= its identity) between runs.
"""

import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from server import STORES_DIR, StoreServer


@pytest.fixture
def scan(tmp_path, monkeypatch):
    monkeypatch.setenv("ECI_LOG_DIR", str(tmp_path / "logs"))
    config = tmp_path / "config.yaml"
    config.write_text(f"db_path: {(tmp_path / 'intel.db').as_posix()}\nrate_limit_delay: 0\n", encoding="utf-8")
    runs = []

    def run(*urls):
        import main
        sites = tmp_path / "sites.txt"
        sites.write_text("\n".join(urls) + "\n", encoding="utf-8")
        out = tmp_path / f"out{len(runs) + 1}"
        result = CliRunner().invoke(main.main, ["--sites", str(sites), "--outdir", str(out), "--config",
                                                str(config), "--lang", "en", "--monitor"])
        assert result.exit_code == 0, result.output
        runs.append(out)
        return (out / "report.md").read_text(encoding="utf-8")

    run.db = tmp_path / "intel.db"
    return run


def _serve_copy(store, dest):
    shutil.copytree(STORES_DIR / store, dest)
    srv = StoreServer(store)
    srv.root = dest.resolve()
    return srv.start()


def _section(md, identity):
    return md.split(f"## 🏪 {identity}", 1)[1].split("\n## ", 1)[0]


def test_price_change_is_reported_on_the_scan_that_saw_it(tmp_path, scan):
    root = tmp_path / "store"
    srv = _serve_copy("shopify_basic", root)
    try:
        identity = srv.base_url.split("//", 1)[1]
        first = scan(srv.base_url)
        assert "First scan" in _section(first, identity)

        for page in root.rglob("*.html"):
            page.write_text(page.read_text(encoding="utf-8").replace("39.00", "44.00"), encoding="utf-8")
        second = scan(srv.base_url)
        assert "Highest price changed from $39.0 to $44.0" in _section(second, identity)

        third = scan(srv.base_url)
        section = _section(third, identity)
        assert "Highest price changed" not in section
        assert "No notable change since the last scan" in section
    finally:
        srv.stop()


def test_two_local_stores_on_different_ports_have_separate_histories(tmp_path, scan):
    from modules.snapshot_store import SnapshotStore
    shop = _serve_copy("shopify_basic", tmp_path / "shop")
    woo = _serve_copy("woocommerce_promo", tmp_path / "woo")
    try:
        ids = [srv.base_url.split("//", 1)[1] for srv in (shop, woo)]
        scan(shop.base_url, woo.base_url)
        second = scan(shop.base_url, woo.base_url)
        for identity in ids:
            section = _section(second, identity)
            assert "No notable change since the last scan" in section, section[:400]
            assert "changed from" not in section
        store = SnapshotStore(str(scan.db))
        assert [store.get_scan_count(identity) for identity in ids] == [2, 2]
    finally:
        shop.stop()
        woo.stop()


def test_site_identity_keeps_the_port():
    from modules.url_utils import site_identity
    assert site_identity("http://127.0.0.1:8899") != site_identity("http://127.0.0.1:8900")
    assert site_identity("http://127.0.0.1:8899/shop") == "127.0.0.1:8899"
    assert site_identity("https://www.example.com/") == "example.com"
    assert site_identity("https://shop.example.com:8443") == "example.com:8443"
