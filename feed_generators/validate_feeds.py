"""Validate every enabled RSS output declared in feeds.yaml."""

from __future__ import annotations

from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def require_text(parent: ElementTree.Element, tag: str, context: str) -> str:
    value = parent.findtext(tag, default="").strip()
    if not value:
        raise ValueError(f"{context} is missing {tag}.")
    return value


def validate_feed(path: Path) -> int:
    root = ElementTree.parse(path).getroot()
    if root.tag != "rss" or root.get("version") != "2.0":
        raise ValueError(f"{path.name} is not RSS 2.0.")

    channel = root.find("channel")
    if channel is None:
        raise ValueError(f"{path.name} has no channel.")
    require_text(channel, "title", path.name)
    require_text(channel, "link", path.name)
    require_text(channel, "description", path.name)

    items = channel.findall("item")
    if not items:
        raise ValueError(f"{path.name} has no items.")

    guids: set[str] = set()
    for index, item in enumerate(items, start=1):
        context = f"{path.name} item {index}"
        require_text(item, "title", context)
        require_text(item, "link", context)
        guid = require_text(item, "guid", context)
        if guid in guids:
            raise ValueError(f"{path.name} contains duplicate GUID {guid}.")
        guids.add(guid)
        published = item.findtext("pubDate", default="").strip()
        if published:
            parsedate_to_datetime(published)
    return len(items)


def main() -> None:
    registry = yaml.safe_load((PROJECT_ROOT / "feeds.yaml").read_text(encoding="utf-8"))
    feeds = registry.get("feeds", {})
    if not feeds:
        raise RuntimeError("No feeds are registered.")

    for name, config in feeds.items():
        if not config.get("enabled", True):
            continue
        path = PROJECT_ROOT / config["output"]
        count = validate_feed(path)
        print(f"{name}: valid ({count} items)")


if __name__ == "__main__":
    main()
