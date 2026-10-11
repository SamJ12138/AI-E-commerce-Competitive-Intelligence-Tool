"""requirements.txt lists exactly what the code imports (B1)."""

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SOURCES = [REPO / "main.py"] + sorted((REPO / "modules").glob("*.py"))

# distribution name -> import name, where they differ
IMPORT_NAME = {"beautifulsoup4": "bs4", "pyyaml": "yaml"}
# used without an import statement: (file, literal that proves the use)
USED_WITHOUT_IMPORT = {"lxml": ("modules/http_client.py", "'lxml'")}
REMOVED = {"xgboost", "scikit-learn", "numpy", "html5lib", "pandas", "sqlite-utils",
           "python-dateutil", "html2text", "ratelimit", "deepdiff"}


def _requirements():
    names = []
    for line in (REPO / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            names.append(re.split(r"[<>=!~\[ ;]", line, maxsplit=1)[0].lower())
    return names


def _imported_top_level():
    found = set()
    for path in SOURCES:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                found |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                found.add(node.module.split(".")[0])
    return found


def test_removed_packages_are_not_required():
    assert not set(_requirements()) & REMOVED, sorted(set(_requirements()) & REMOVED)


def test_every_requirement_is_used():
    imported = _imported_top_level()
    unused = []
    for name in _requirements():
        if name in USED_WITHOUT_IMPORT:
            rel, literal = USED_WITHOUT_IMPORT[name]
            if literal not in (REPO / rel).read_text(encoding="utf-8"):
                unused.append(name)
        elif IMPORT_NAME.get(name, name.replace("-", "_")) not in imported:
            unused.append(name)
    assert not unused, f"listed in requirements.txt but never imported: {unused}"
