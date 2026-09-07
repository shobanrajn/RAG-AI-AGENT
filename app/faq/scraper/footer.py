from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.faq.logging import faq_log
from .fetcher import fetch_url, clean_html, html_to_markdown
from .scraper_utils import is_scrapable_url, save_debug_file, url_hash
from .parser import parse_sections, sections_to_chunks
from .stop import is_stop_requested

HEADING_TAGS = {"h2", "h3", "h4", "h5", "strong", "b"}


def extract_footer_topics(soup: BeautifulSoup, base_url: str) -> dict:
    footer = soup.find("footer")
    if not footer:
        faq_log.warning("[SCRAPER] No <footer> tag found")
        return {}

    all_topics = {}
    for container in footer.find_all(True):
        if container.name not in HEADING_TAGS:
            continue
        topic_name = container.get_text(strip=True)
        if not topic_name or len(topic_name) > 60:
            continue
        links = []
        for sibling in container.find_next_siblings():
            if sibling.name in HEADING_TAGS:
                break
            for a in (sibling.find_all("a") if sibling.name != "a" else [sibling]):
                href = a.get("href", "").strip()
                text = a.get_text(strip=True)
                if href and text:
                    links.append({"text": text, "url": urljoin(base_url, href)})
        if links:
            all_topics[topic_name] = links
    return all_topics


def scrape_page(url: str, topic: str = "", link_text: str = "") -> list:
    faq_log.info("[SCRAPER] Scraping: %s", url)
    try:
        uhash = url_hash(url)
        html = fetch_url(url)
        save_debug_file(f"raw_{uhash}.html", html)

        clean = clean_html(html)
        markdown = html_to_markdown(clean)
        save_debug_file(f"page_{uhash}.md", markdown)

        sections = parse_sections(markdown)
        save_debug_file(f"extracted_{uhash}.json", sections)

        chunks = sections_to_chunks(sections, url, topic, link_text)
        save_debug_file(f"chunks_{uhash}.json", chunks)

        faq_log.info("[SCRAPER] %s → %d chunks", url, len(chunks))
        return chunks
    except Exception as e:
        faq_log.error("[SCRAPER] Failed: %s | %s: %s", url, type(e).__name__, e)
        return []


def scrape_footer_topics(base_url: str, wanted_topics: list) -> list:
    faq_log.info("[SCRAPER] Extracting footer from: %s", base_url)
    html = fetch_url(base_url)
    soup = BeautifulSoup(html, "html.parser")

    all_topics = extract_footer_topics(soup, base_url)
    save_debug_file("footer_all_topics.json", all_topics)
    faq_log.info("[SCRAPER] Found footer topics: %s", list(all_topics.keys()))

    missing = [t for t in wanted_topics if t not in all_topics]
    if missing:
        faq_log.warning("[SCRAPER] Topics not found in footer: %s", missing)

    all_chunks: list = []
    seen_urls: set = set()

    for topic in wanted_topics:
        if topic not in all_topics:
            continue
        faq_log.info("[SCRAPER] Topic: %s | %d links", topic, len(all_topics[topic]))
        for link in all_topics[topic]:
            if is_stop_requested():
                faq_log.warning("[SCRAPER] Stop requested — halting scraping")
                return all_chunks
            url = link["url"]
            if url in seen_urls or not is_scrapable_url(url, base_url):
                continue
            seen_urls.add(url)
            all_chunks.extend(scrape_page(url, topic=topic, link_text=link["text"]))

    return all_chunks
