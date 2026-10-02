"""Generate an RSS feed for the public @SulakeDominic X timeline."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
import re
import sys
from xml.etree import ElementTree
from xml.etree.ElementTree import Element, SubElement, indent

from playwright.sync_api import Page, sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCREEN_NAME = "SulakeDominic"
PROFILE_URL = f"https://x.com/{SCREEN_NAME}"
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


def make_title(text: str) -> str:
    title = " ".join(text.split())
    if not title:
        return f"Post by @{SCREEN_NAME}"
    if len(title) <= 120:
        return title
    return title[:117].rstrip() + "..."


def extract_visible_posts(page: Page) -> list[Post]:
    """Extract @SulakeDominic's own posts from X's rendered profile."""
    posts: dict[str, Post] = {}
    status_pattern = re.compile(rf"^/{re.escape(SCREEN_NAME)}/status/(\d+)$", re.IGNORECASE)

    for article in page.locator("article").all():
        links = article.locator(f'a[href^="/{SCREEN_NAME}/status/"]')
        permalink = ""
        tweet_id = ""
        date_link = None
        for index in range(links.count()):
            link = links.nth(index)
            href = link.get_attribute("href") or ""
            match = status_pattern.match(href)
            if match:
                permalink = href
                tweet_id = match.group(1)
                date_link = link
                break

        if not permalink or not tweet_id or date_link is None:
            continue

        text_container = date_link.locator("xpath=../../../..").locator(":scope > div").nth(1)
        if not text_container.count():
            continue

        show_more = text_container.get_by_role("button", name="Show more").first
        if show_more.count():
            try:
                show_more.click(timeout=2_000)
            except Exception:
                # The visible text is still usable if X removes the button mid-render.
                pass

        text = text_container.inner_text().removesuffix(" Show more").strip()
        text = "\n".join(line.rstrip() for line in text.splitlines())
        if not text:
            continue

        link = f"https://x.com{permalink}"
        published_ms = (int(tweet_id) >> 22) + 1_288_834_974_657
        posts[link] = Post(
            guid=link,
            title=make_title(text),
            link=link,
            published=datetime.fromtimestamp(published_ms / 1000, tz=UTC),
            description=text,
        )

    return list(posts.values())


def fetch_posts() -> list[Post]:
    """Render the public X profile and collect several screens of posts."""
    with sync_playwright() as playwright:
        installed_chrome = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
        launch_options: dict[str, object] = {
            "headless": sys.platform != "win32",
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--window-position=-32000,-32000",
            ],
        }
        if installed_chrome.exists():
            launch_options["executable_path"] = str(installed_chrome)
        browser = playwright.chromium.launch(
            **launch_options,
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 1600},
            locale="en-GB",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/153.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        page.goto(PROFILE_URL, wait_until="domcontentloaded", timeout=60_000)
        page.locator(f'a[href^="/{SCREEN_NAME}/status/"]').first.wait_for(timeout=45_000)

        collected: dict[str, Post] = {}
        unchanged_rounds = 0
        for _ in range(8):
            before = len(collected)
            collected.update({post.guid: post for post in extract_visible_posts(page)})
            if len(collected) == before:
                unchanged_rounds += 1
            else:
                unchanged_rounds = 0
            if unchanged_rounds >= 2 or len(collected) >= 40:
                break
            page.mouse.wheel(0, 1400)
            page.wait_for_timeout(1_500)

        browser.close()

    if not collected:
        raise RuntimeError("No public @SulakeDominic posts were found on the rendered profile.")
    return list(collected.values())


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

    if sys.platform != "win32":
        existing = load_existing_posts(args.output)
        if not existing:
            raise RuntimeError("The SulakeDominic feed requires the Windows local updater.")
        print(
            f"{args.output}: kept existing feed ({len(existing)} posts); "
            "the Windows local updater owns this feed"
        )
        return

    try:
        current = fetch_posts()
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
