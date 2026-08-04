"""Generate an RSS feed from the JavaScript-rendered Habbo Origins news page."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin
from xml.etree.ElementTree import Element, ElementTree, SubElement, indent

from playwright.sync_api import Page, sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SITE_URL = "https://origins.habbo.com/community/category/all/1"
FEED_URL = (
    "https://raw.githubusercontent.com/nert69/rss-feeds/"
    "main/habbo-origins-community.rss"
)
DEFAULT_OUTPUT = PROJECT_ROOT / "habbo-origins-community.rss"


@dataclass(frozen=True)
class Article:
    title: str
    link: str
    published: datetime | None


def normalise_title(raw_title: str) -> str:
    """Undo the source page's all-caps titles without mangling mixed-case text."""
    title = " ".join(raw_title.split())
    if any(character.isalpha() for character in title) and title == title.upper():
        return " ".join(
            word[:1].upper() + word[1:].lower() if word else word
            for word in title.split(" ")
        )
    return title


def parse_date(raw_date: str) -> datetime | None:
    for date_format in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(raw_date.strip(), date_format).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def scrape_articles(page: Page) -> list[Article]:
    page.goto(SITE_URL, wait_until="domcontentloaded", timeout=45_000)
    page.wait_for_selector("article.news-header", timeout=30_000)

    articles: list[Article] = []
    seen_links: set[str] = set()
    for card in page.locator("article.news-header").all():
        title_element = card.locator("h2.news-header__title")
        link_element = card.locator("a.news-header__link.news-header__banner")
        date_element = card.locator("time.news-header__date")

        if title_element.count() == 0 or link_element.count() == 0:
            continue

        title = normalise_title(title_element.first.inner_text())
        href = link_element.first.get_attribute("href") or ""
        link = urljoin(SITE_URL, href)
        raw_date = date_element.first.inner_text() if date_element.count() else ""

        if title and href and link not in seen_links:
            articles.append(Article(title=title, link=link, published=parse_date(raw_date)))
            seen_links.add(link)

    if not articles:
        raise RuntimeError("No Habbo Origins articles were found; refusing to replace the feed.")
    return articles


def rfc_822(value: datetime) -> str:
    return value.strftime("%a, %d %b %Y %H:%M:%S +0000")


def build_feed(articles: list[Article]) -> bytes:
    rss = Element(
        "rss",
        {
            "version": "2.0",
            "xmlns:atom": "http://www.w3.org/2005/Atom",
        },
    )
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = "Habbo Hotel Origins — Community News"
    SubElement(channel, "link").text = SITE_URL
    SubElement(channel, "description").text = "Latest news from Habbo Hotel Origins"
    SubElement(channel, "language").text = "en"
    SubElement(
        channel,
        "atom:link",
        {"href": FEED_URL, "rel": "self", "type": "application/rss+xml"},
    )

    newest_date = next((article.published for article in articles if article.published), None)
    if newest_date:
        SubElement(channel, "lastBuildDate").text = rfc_822(newest_date)

    for article in articles:
        item = SubElement(channel, "item")
        SubElement(item, "title").text = article.title
        SubElement(item, "link").text = article.link
        SubElement(item, "guid", {"isPermaLink": "true"}).text = article.link
        if article.published:
            SubElement(item, "pubDate").text = rfc_822(article.published)
        SubElement(item, "description").text = article.title

    indent(rss, space="  ")
    from io import BytesIO

    buffer = BytesIO()
    ElementTree(rss).write(buffer, encoding="utf-8", xml_declaration=True)
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

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            articles = scrape_articles(page)
        finally:
            browser.close()

    changed = write_if_changed(args.output, build_feed(articles))
    state = "updated" if changed else "already current"
    print(f"{args.output}: {state} ({len(articles)} articles)")


if __name__ == "__main__":
    main()
