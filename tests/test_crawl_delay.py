"""robots.txt Crawl-delay: the per-host delay is max(config rate_limit_delay, Crawl-delay)."""

import json

import pytest

import main
from modules import obs
from modules.http_client import HttpClient
from modules.models import Config
from modules.robots_checker import RobotsChecker
from server import StoreServer

RULES = "User-agent: *\nDisallow: /cart\n"


def _events(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _run(tmp_path, robots_txt, config_delay, **cfg):
    run_id = obs.init_run(log_dir=str(tmp_path), run_id="cd")
    try:
        with StoreServer("shopify_basic", robots_txt=robots_txt) as srv:
            config = Config(rate_limit_delay=config_delay, timeout=10, **cfg)
            client = HttpClient(config)
            try:
                main.analyze_site(srv.base_url, client, RobotsChecker(config), config)
                host = srv.base_url.split("//", 1)[1]
                delay = client.rate_limiter.delay_for(host)
            finally:
                client.close()
            seen = srv.request_log()
    finally:
        obs.close_run()
    events = [e for e in _events(tmp_path / f"run_{run_id}.jsonl") if e["context"].get("kind") == "crawl_delay"]
    return delay, seen, events


def _page_gaps(seen):
    pages = [r["ts"] for r in seen if r["path"] != "/robots.txt"]
    return [b - a for a, b in zip(pages, pages[1:])]


def test_absent_keeps_the_config_delay(tmp_path):
    delay, seen, events = _run(tmp_path, RULES, 0.2)
    assert delay == 0.2
    assert [e["context"]["raised"] for e in events] == [False]
    assert events[0]["context"]["crawl_delay"] is None


def test_smaller_keeps_the_config_delay(tmp_path):
    delay, seen, events = _run(tmp_path, RULES + "Crawl-delay: 0.05\n", 0.3)
    assert delay == 0.3
    assert [(e["context"]["crawl_delay"], e["context"]["raised"]) for e in events] == [(0.05, False)]


def test_larger_raises_the_delay_and_is_logged(tmp_path, caplog):
    caplog.set_level("INFO")
    delay, seen, events = _run(tmp_path, RULES + "Crawl-delay: 0.6\n", 0.1)
    assert delay == 0.6
    (e,) = events
    assert e["event"] == "success"
    assert (e["context"]["crawl_delay"], e["context"]["config_delay"], e["context"]["delay"],
            e["context"]["raised"]) == (0.6, 0.1, 0.6, True)
    assert any("Crawl-delay" in r.getMessage() and "0.6" in r.getMessage() for r in caplog.records)
    gaps = _page_gaps(seen)
    assert len(gaps) >= 3 and min(gaps) >= 0.55, gaps


def test_a_group_with_only_a_crawl_delay_line_counts(tmp_path):
    # robotexclusionrulesparser drops a group that has no Allow/Disallow line.
    delay, _, _ = _run(tmp_path, "User-agent: *\nCrawl-delay: 0.4\n", 0.0)
    assert delay == 0.4


def test_crawl_delay_for_another_agent_does_not_apply(tmp_path):
    delay, _, _ = _run(tmp_path, "User-agent: Googlebot\nCrawl-delay: 5\n\n" + RULES, 0.1)
    assert delay == 0.1


def test_ignore_robots_ignores_crawl_delay(tmp_path):
    delay, _, events = _run(tmp_path, RULES + "Crawl-delay: 0.6\n", 0.1, ignore_robots=True)
    assert delay == 0.1 and not [e for e in events if e["context"].get("raised")]
