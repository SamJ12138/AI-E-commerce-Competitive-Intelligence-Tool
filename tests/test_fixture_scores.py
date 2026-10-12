"""Batch 7 gate: main.py, run end to end on each fixture store, matches its ground truth.

Uses scripts/score_fixtures.py (same runs, same scoring) with rate_limit_delay 0. Both
answering stores must match every field of fixtures.json; the blocked store must be all
null with status=blocked. The --render-js run needs a browser and only runs when
ECI_TEST_RENDER_JS=1.
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import score_fixtures as sf  # noqa: E402

RUNS = [r for r in sf.RUNS if "--render-js" not in r[2] or os.environ.get("ECI_TEST_RENDER_JS") == "1"]


@pytest.fixture(scope="module")
def scored(tmp_path_factory):
    out_root = tmp_path_factory.mktemp("fixture_runs")
    return {label: sf.score_run(sf.run_one(label, store, extra, out_root, sys.executable,
                                           config_extra={"rate_limit_delay": 0}))
            for label, store, extra in RUNS}


@pytest.mark.parametrize("label", [r[0] for r in RUNS])
def test_every_ground_truth_field_matches(scored, label):
    run = scored[label]
    assert run["exit_code"] == 0, f"main.py exited {run['exit_code']}, see {run['log']}"
    wrong = [f"{f['field']}: expected {f['expected']!r}, got {f['got']!r} ({f['verdict']}; {f['source']})"
             for f in run["fields"] if f["verdict"] != "match"]
    assert not wrong, "\n".join(wrong)
    assert run["checks"]["status"] == run["checks"]["expected_status"]


@pytest.mark.parametrize("label", [r[0] for r in RUNS if r[1] == "blocked"])
def test_blocked_store_is_all_null(scored, label):
    run = scored[label]
    assert run["checks"]["status"] == "blocked"
    assert run["checks"]["fetch_attempts"]
    assert [f["field"] for f in run["fields"] if f["got"] not in (None, [])] == []
