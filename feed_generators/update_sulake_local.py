"""Refresh the SulakeDominic feed locally and publish changes to GitHub."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GENERATOR = Path(__file__).with_name("sulake_dominic.py")
FEED = PROJECT_ROOT / "sulake-dominic.rss"


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(
        args,
        cwd=PROJECT_ROOT,
        env=environment,
        check=check,
        text=True,
        timeout=180,
    )


def main() -> None:
    run(sys.executable, str(GENERATOR), "--output", str(FEED))
    run("git", "add", "--", FEED.name)
    if run("git", "diff", "--cached", "--quiet", check=False).returncode == 0:
        print("SulakeDominic RSS is already current.")
        return
    run("git", "commit", "-m", "Update SulakeDominic RSS feed")
    run("git", "push", "origin", "main")
    print("Published the updated SulakeDominic RSS feed.")


if __name__ == "__main__":
    main()
