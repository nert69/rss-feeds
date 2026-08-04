"""Run every enabled feed generator in feeds.yaml."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PROJECT_ROOT / "feeds.yaml"
GENERATOR_DIR = PROJECT_ROOT / "feed_generators"


def load_feeds() -> dict[str, dict[str, object]]:
    registry = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    feeds = registry.get("feeds")
    if not isinstance(feeds, dict) or not feeds:
        raise RuntimeError("feeds.yaml must contain a non-empty 'feeds' mapping.")
    return feeds


def main() -> int:
    failures: list[str] = []
    for name, config in load_feeds().items():
        if not isinstance(config, dict):
            raise RuntimeError(f"Feed '{name}' must be a mapping.")
        if not config.get("enabled", True):
            print(f"Skipping disabled feed: {name}")
            continue

        script_name = config.get("script")
        output_name = config.get("output")
        if not isinstance(script_name, str) or not isinstance(output_name, str):
            raise RuntimeError(f"Feed '{name}' needs string script and output values.")

        script = (GENERATOR_DIR / script_name).resolve()
        if script.parent != GENERATOR_DIR.resolve() or not script.is_file():
            raise RuntimeError(f"Feed '{name}' references an invalid script: {script_name}")

        output = (PROJECT_ROOT / output_name).resolve()
        if PROJECT_ROOT.resolve() not in output.parents:
            raise RuntimeError(f"Feed '{name}' references an invalid output: {output_name}")

        print(f"Generating {name}...")
        result = subprocess.run(
            [sys.executable, str(script), "--output", str(output)],
            cwd=PROJECT_ROOT,
            check=False,
        )
        if result.returncode != 0:
            failures.append(name)

    if failures:
        print(f"Failed feeds: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
