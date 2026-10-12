"""Repository hygiene: no personal data in tracked files, a license, a config example that matches
what the code reads."""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

# Built from pieces so that this file does not match itself.
BS = chr(92)
PERSONAL = {
    "school domain": re.compile("gettys" + "burg", re.I),
    "school login": re.compile("jia" + "ti", re.I),
    "local account": re.compile("isa" + "mb", re.I),
    "mail provider": re.compile("gma" + "il", re.I),
    "Windows home path": re.compile("[A-Za-z]:(?:" + BS * 2 + "{1,2}|/)" + "Us" + "ers" + "(?:" + BS * 2 + "{1,2}|/)", re.I),
    "Linux home path": re.compile("/" + "home" + "/"),
}


def _tracked_files():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, check=True).stdout
    return [REPO / p for p in out.decode("utf-8").split("\0") if p]


def test_no_personal_data_in_tracked_files():
    hits = []
    for path in _tracked_files():
        if not path.is_file():
            continue
        text = path.read_bytes().decode("utf-8", "replace")
        rel = path.relative_to(REPO).as_posix()
        for name, pattern in PERSONAL.items():
            for m in pattern.finditer(rel + "\n" + text):
                hits.append(f"{rel}: {name}: {m.group(0)!r}")
    assert not hits, "\n".join(hits[:50])


def test_license_and_notice():
    text = (REPO / "LICENSE").read_text(encoding="utf-8")
    assert text.startswith("MIT License") and "Copyright (c) 2026 Tianyi Jia" in text
    assert (REPO / "NOTICE.md").is_file()


def test_real_config_is_ignored():
    assert subprocess.run(["git", "check-ignore", "-q", "config.yaml"], cwd=REPO).returncode == 0


def _documented_keys():
    lines = (REPO / "config.example.yaml").read_text(encoding="utf-8").splitlines()
    keys = {}
    for i, line in enumerate(lines):
        m = re.match(r"^#?\s?([a-z_]+):", line)
        if m and not line.startswith("# "):
            documented = "#" in line.split(":", 1)[1] or (i and lines[i - 1].lstrip().startswith("#"))
            keys[m.group(1)] = bool(documented)
    return keys


def test_config_example_documents_every_key_the_code_reads():
    import main
    keys = _documented_keys()
    assert set(keys) == set(main.CONFIG_KEYS)
    assert all(keys.values()), [k for k, ok in keys.items() if not ok]
    data = yaml.safe_load((REPO / "config.example.yaml").read_text(encoding="utf-8")) or {}
    for key, value in data.items():   # the values shown are the defaults
        assert value == main.CONFIG_KEYS[key], key


@pytest.mark.parametrize("cli,expected", [
    ([], {"timeout": 7, "max_pages": 3, "max_products": 4, "rate_limit_delay": 0.0}),
    (["--max-pages", "5", "--timeout", "9"], {"timeout": 9, "max_pages": 5, "max_products": 4}),
])
def test_config_file_values_are_used_unless_the_cli_sets_them(tmp_path, cli, expected):
    import score_fixtures
    run = score_fixtures.run_one("cfg", "blocked", cli, tmp_path, sys.executable,
                                 config_extra={"timeout": 7, "max_pages": 3, "max_products": 4,
                                               "rate_limit_delay": 0})
    events = [json.loads(line) for line in Path(run["log"]).read_text(encoding="utf-8").splitlines()]
    (resolved,) = [e["context"] for e in events if e["context"].get("kind") == "config_resolved"]
    assert {k: resolved[k] for k in expected} == expected


def test_baseline_logs_are_written_without_local_paths(tmp_path):
    import score_fixtures
    root = str(REPO)
    text = json.dumps({"a": root + BS + "output", "b": Path(root).as_posix() + "/x", "c": str(tmp_path)})
    out = score_fixtures.scrub_paths(text, {REPO: "<repo>", tmp_path: "<out>"})
    assert json.loads(out) == {"a": "<repo>" + BS + "output", "b": "<repo>/x", "c": "<out>"}
