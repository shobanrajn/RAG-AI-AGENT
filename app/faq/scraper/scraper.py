from datetime import datetime
from ..config import faq_log, SCRAPER_URLS, FOOTER_BASE_URL, FOOTER_TOPICS, PG_FAQ_TABLE, GEMINI_EMBEDDING_MODEL
from .stop import is_stop_requested
from .footer import scrape_page, scrape_footer_topics
from .embedder import store_embeddings
from .scraper_utils import save_debug_file


def run() -> None:
    faq_log.info("[SCRAPER] Starting scraper run")

    seen_texts: set = set()
    all_chunks: list = []

    def add_chunks(chunks: list) -> None:
        for chunk in chunks:
            if chunk["text"] not in seen_texts:
                seen_texts.add(chunk["text"])
                all_chunks.append(chunk)

    if SCRAPER_URLS:
        faq_log.info("[SCRAPER] Scraping %d direct URL(s)", len(SCRAPER_URLS))
        for url in SCRAPER_URLS:
            if is_stop_requested():
                faq_log.warning("[SCRAPER] Stop requested — halting scraping")
                return
            add_chunks(scrape_page(url))

    if FOOTER_BASE_URL and FOOTER_TOPICS:
        faq_log.info("[SCRAPER] Scraping footer topics: %s", FOOTER_TOPICS)
        add_chunks(scrape_footer_topics(FOOTER_BASE_URL, FOOTER_TOPICS))

    if not all_chunks:
        faq_log.warning("[SCRAPER] No chunks extracted. Check SCRAPER_URLS or FOOTER_BASE_URL in .env")
        return

    faq_log.info("[SCRAPER] Total unique chunks: %d", len(all_chunks))
    save_debug_file(f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", {
        "timestamp": datetime.now().isoformat(),
        "total_chunks": len(all_chunks),
        "scraper_urls": SCRAPER_URLS,
        "footer_base_url": FOOTER_BASE_URL,
        "footer_topics": FOOTER_TOPICS,
        "table": PG_FAQ_TABLE,
        "embedding_model": GEMINI_EMBEDDING_MODEL,
    })

    store_embeddings(all_chunks)
    faq_log.info("[SCRAPER] Scraping complete")


if __name__ == "__main__":
    run()
