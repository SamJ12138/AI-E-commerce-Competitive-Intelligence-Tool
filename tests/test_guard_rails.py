"""Batch 7: the pre-commit hook, its installer and the CI workflow."""

import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / "scripts" / "hooks" / "pre-commit"
INSTALLER = REPO / "scripts" / "install-hooks.py"
WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"


def test_hook_runs_the_full_suite():
    text = HOOK.read_text(encoding="utf-8")
    assert text.startswith("#!/bin/sh")
    assert "-m pytest" in text and "exit 1" in text
    assert " -k " not in text and "--deselect" not in text   # the whole suite, nothing skipped


def test_installer_copies_the_hook(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    result = subprocess.run([sys.executable, str(INSTALLER), "--repo", str(tmp_path)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    installed = tmp_path / ".git" / "hooks" / "pre-commit"
    assert installed.read_bytes() == HOOK.read_bytes()


def test_installer_keeps_a_different_existing_hook(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    existing = tmp_path / ".git" / "hooks" / "pre-commit"
    existing.write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
    result = subprocess.run([sys.executable, str(INSTALLER), "--repo", str(tmp_path)],
                            capture_output=True, text=True)
    assert result.returncode != 0 and "--force" in result.stderr
    assert existing.read_text(encoding="utf-8") == "#!/bin/sh\necho mine\n"


def test_ci_workflow():
    wf = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    job = next(iter(wf["jobs"].values()))
    matrix = job["strategy"]["matrix"]
    assert sorted(matrix["os"]) == ["ubuntu-24.04", "windows-2025"]
    assert [str(v) for v in matrix["python-version"]] == ["3.12"]
    uses = [step["uses"] for step in job["steps"] if "uses" in step]
    assert "actions/checkout@v5" in uses and "actions/setup-python@v6" in uses   # both run on Node 24
    runs = "\n".join(step.get("run", "") for step in job["steps"])
    assert "pip install -r requirements-dev.txt" in runs and "-m pytest" in runs
    dev = (REPO / "requirements-dev.txt").read_text(encoding="utf-8").splitlines()
    assert "-r requirements.txt" in dev and any(line.startswith("pytest") for line in dev)
    assert True in wf or "on" in wf   # PyYAML reads the bare key `on` as True
