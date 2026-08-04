"""Generate an RSS feed for the public @SulakeDominic X timeline."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement, indent

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCREEN_NAME = "SulakeDominic"
PROFILE_URL = f"https://x.com/{SCREEN_NAME}"
SOURCE_URL = (
    "https://syndication.twitter.com/srv/timeline-profile/"
    f"screen-name/{SCREEN_NAME}"
)
FEED_URL = (
    "https://raw.githubusercontent.com/nert69/rss-feeds/"
    "main/sulake-dominic.rss"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "sulake-dominic.rss"
MAX_ITEMS = 100


@dataclass(frozen=True)
class Post:
    guid: str
    title: str
    link: str
    published: datetime
    description: str


class NextDataParser(HTMLParser):
    """Extract the JSON payload from X's server-rendered syndication page."""

    def __init__(self) -> None:
        super().__init__()
        self.in_next_data = False
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "script" and attributes.get("id") == "__NEXT_DATA__":
            self.in_next_data = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self.in_next_data:
            self.in_next_data = False

    def handle_data(self, data: str) -> None:
        if self.in_next_data:
            self.parts.append(data)

    @property
    def json_text(self) -> str:
        return "".join(self.parts)


def fetch_timeline_data() -> dict[str, object]:
    request = Request(
        SOURCE_URL,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; nert69-rss-feeds/1.0; "
                "+https://github.com/nert69/rss-feeds)"
            )
        },
    )
    with urlopen(request, timeout=30) as response:
        html = response.read().decode("utf-8")

    parser = NextDataParser()
    parser.feed(html)
    if not parser.json_text:
        raise RuntimeError("X syndication page did not contain its timeline data.")
    data = json.loads(parser.json_text)
    if not isinstance(data, dict):
        raise RuntimeError("X syndication timeline data had an unexpected format.")
    return data


def parse_x_date(value: str) -> datetime:
    return datetime.strptime(value, "%a %b %d %H:%M:%S %z %Y").astimezone(UTC)


def make_title(text: str) -> str:
    title = " ".join(text.split())
    if not title:
        return f"Post by @{SCREEN_NAME}"
    if len(title) <= 120:
        return title
    return title[:117].rstrip() + "..."


def parse_posts(data: dict[str, object]) -> list[Post]:
    try:
        entries = data["props"]["pageProps"]["timeline"]["entries"]  # type: ignore[index]
    except (KeyError, TypeError) as error:
        raise RuntimeError("X syndication response did not include timeline entries.") from error
    if not isinstance(entries, list):
        raise RuntimeError("X syndication timeline entries had an unexpected format.")

    posts: list[Post] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("type") != "tweet":
            continue
        content = entry.get("content", {})
        if not isinstance(content, dict):
            continue
        tweet = content.get("tweet", {})
        if not isinstance(tweet, dict):
            continue
        user = tweet.get("user", {})
        if not isinstance(user, dict) or str(user.get("screen_name", "")).casefold() != SCREEN_NAME.casefold():
            continue

        tweet_id = str(tweet.get("id_str", "")).strip()
        text = str(tweet.get("full_text") or tweet.get("text") or "").strip()
        text = "\n".join(line.rstrip() for line in text.splitlines())
        permalink = str(tweet.get("permalink", "")).strip()
        created_at = str(tweet.get("created_at", "")).strip()
        if not tweet_id or not text or not permalink or not created_at or tweet_id in seen:
            continue

        link = urljoin("https://x.com", permalink)
        posts.append(
            Post(
                guid=link,
                title=make_title(text),
                link=link,
                published=parse_x_date(created_at),
                description=text,
            )
        )
        seen.add(tweet_id)

    if not posts:
        raise RuntimeError("No public @SulakeDominic posts were found; refusing to replace the feed.")
    return posts


def load_existing_posts(path: Path) -> list[Post]:
    if not path.exists():
        return []
    try:
        channel = ElementTree.parse(path).getroot().find("channel")
    except ElementTree.ParseError:
        return []
    if channel is None:
        return []

    posts: list[Post] = []
    for item in channel.findall("item"):
        guid = item.findtext("guid", default="").strip()
        title = item.findtext("title", default="").strip()
        link = item.findtext("link", default="").strip()
        published = item.findtext("pubDate", default="").strip()
        description = item.findtext("description", default="").strip()
        if not guid or not title or not link or not published:
            continue
        try:
            published_at = parsedate_to_datetime(published).astimezone(UTC)
        except (TypeError, ValueError):
            continue
        posts.append(Post(guid, title, link, published_at, description))
    return posts


def merge_posts(current: list[Post], existing: list[Post]) -> list[Post]:
    merged = {post.guid: post for post in existing}
    merged.update({post.guid: post for post in current})
    return sorted(merged.values(), key=lambda post: post.published, reverse=True)[:MAX_ITEMS]


def rfc_822(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%a, %d %b %Y %H:%M:%S +0000")


def build_feed(posts: list[Post]) -> bytes:
    rss = Element(
        "rss",
        {
            "version": "2.0",
            "xmlns:atom": "http://www.w3.org/2005/Atom",
        },
    )
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = f"Macklebee (@{SCREEN_NAME}) - X posts"
    SubElement(channel, "link").text = PROFILE_URL
    SubElement(channel, "description").text = f"Public posts from @{SCREEN_NAME} on X"
    SubElement(channel, "language").text = "en"
    SubElement(
        channel,
        "atom:link",
        {"href": FEED_URL, "rel": "self", "type": "application/rss+xml"},
    )
    SubElement(channel, "lastBuildDate").text = rfc_822(posts[0].published)

    for post in posts:
        item = SubElement(channel, "item")
        SubElement(item, "title").text = post.title
        SubElement(item, "link").text = post.link
        SubElement(item, "guid", {"isPermaLink": "true"}).text = post.guid
        SubElement(item, "pubDate").text = rfc_822(post.published)
        SubElement(item, "description").text = post.description

    indent(rss, space="  ")
    from io import BytesIO

    buffer = BytesIO()
    ElementTree.ElementTree(rss).write(buffer, encoding="utf-8", xml_declaration=True)
    return buffer.getvalue()


def write_if_changed(output: Path, content: bytes) -> bool:
    if output.exists() and output.read_bytes() == content:
        return False
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(content)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    try:
        current = parse_posts(fetch_timeline_data())
    except (OSError, RuntimeError, ValueError) as error:
        existing = load_existing_posts(args.output)
        if not existing:
            raise
        print(
            f"{args.output}: kept existing feed ({len(existing)} posts); "
            f"X could not be refreshed: {error}"
        )
        return
    posts = merge_posts(current, load_existing_posts(args.output))
    changed = write_if_changed(args.output, build_feed(posts))
    state = "updated" if changed else "already current"
    print(f"{args.output}: {state} ({len(posts)} posts)")


if __name__ == "__main__":
    main()