"""Generate RSS items only for Adobe's Photoshop desktop release notes."""

from __future__ import annotations

import argparse
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen
from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement, indent

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "https://helpx.adobe.com/photoshop/desktop/whats-new/photoshop-on-desktop-release-notes.html"
FEED = "https://raw.githubusercontent.com/nert69/rss-feeds/main/photoshop-release-notes.rss"
VERSION = re.compile(r"^(January|February|March|April|May|June|July|August|September|October|November|December) \d{4} \(version ([\d.]+)\)$", re.I)


class ReleaseParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.heading = False
        self.parts: list[str] = []
        self.releases: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "h2":
            self.heading = True
            self.parts = []

    def handle_data(self, data: str) -> None:
        if self.heading:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "h2" and self.heading:
            title = " ".join("".join(self.parts).split())
            match = VERSION.fullmatch(title)
            if match and title not in (name for name, _ in self.releases):
                self.releases.append((title, match.group(2)))
            self.heading = False


def build_feed(releases: list[tuple[str, str]]) -> bytes:
    rss = Element("rss", {"version": "2.0", "xmlns:atom": "http://www.w3.org/2005/Atom"})
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = "Adobe Photoshop desktop release notes"
    SubElement(channel, "link").text = SOURCE
    SubElement(channel, "description").text = "Official Photoshop desktop version updates and fixes from Adobe."
    SubElement(channel, "language").text = "en"
    SubElement(channel, "atom:link", {"href": FEED, "rel": "self", "type": "application/rss+xml"})
    for title, version in releases:
        item = SubElement(channel, "item")
        SubElement(item, "title").text = f"Photoshop desktop: {title}"
        SubElement(item, "link").text = SOURCE
        SubElement(item, "guid", {"isPermaLink": "false"}).text = f"adobe-photoshop-desktop-{version}"
        SubElement(item, "description").text = f"Official release notes for Photoshop desktop version {version}."
    indent(rss, space="  ")
    return ElementTree.tostring(rss, encoding="utf-8", xml_declaration=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "photoshop-release-notes.rss")
    output = parser.parse_args().output
    try:
        request = Request(SOURCE, headers={"User-Agent": "Mozilla/5.0 (compatible; nert69-rss-feeds/1.0)"})
        with urlopen(request, timeout=30) as response:
            html = response.read().decode("utf-8")
        releases = ReleaseParser()
        releases.feed(html)
        if not releases.releases:
            raise ValueError("Adobe page contained no Photoshop desktop release versions")
        content = build_feed(releases.releases)
    except (OSError, UnicodeError, ValueError) as error:
        if not output.exists():
            raise
        # A failed refresh must never replace a previously validated feed.
        from validate_feeds import validate_feed
        validate_feed(output)
        print(f"{output}: kept existing feed; Adobe could not be refreshed: {error}")
        return
    if output.exists() and output.read_bytes() == content:
        print(f"{output}: already current ({len(releases.releases)} releases)")
        return
    output.write_bytes(content)
    print(f"{output}: updated ({len(releases.releases)} releases)")


if __name__ == "__main__":
    main()
