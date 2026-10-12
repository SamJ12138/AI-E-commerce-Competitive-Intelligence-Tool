#!/usr/bin/env python3
"""
install-hooks.py - Copy scripts/hooks/* into the repository's git hooks directory.

    python scripts/install-hooks.py            # this repository
    python scripts/install-hooks.py --force    # replace a different existing hook

An existing hook with different content is left alone unless --force is given; with
--force the old one is kept next to it as <name>.bak.
"""

import argparse
import filecmp
import shutil
import stat
import subprocess
import sys
from pathlib import Path

SOURCE = Path(__file__).resolve().parent / "hooks"


def hooks_dir(repo: Path) -> Path:
    out = subprocess.run(["git", "-C", str(repo), "rev-parse", "--git-path", "hooks"],
                         capture_output=True, text=True, check=True).stdout.strip()
    path = Path(out)
    return path if path.is_absolute() else repo / path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--force", action="store_true", help="replace a different existing hook (kept as .bak)")
    args = parser.parse_args(argv)

    target_dir = hooks_dir(Path(args.repo).resolve())
    target_dir.mkdir(parents=True, exist_ok=True)
    status = 0
    for hook in sorted(p for p in SOURCE.iterdir() if p.is_file()):
        target = target_dir / hook.name
        if target.exists() and not filecmp.cmp(hook, target, shallow=False):
            if not args.force:
                print(f"{target} exists and differs; left alone (use --force to replace it, "
                      f"the old one is kept as {target.name}.bak)", file=sys.stderr)
                status = 1
                continue
            shutil.copy2(target, target.with_name(target.name + ".bak"))
        shutil.copyfile(hook, target)
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        print(f"installed {target}")
    return status


if __name__ == "__main__":
    sys.exit(main())
