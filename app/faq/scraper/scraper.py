from datetime import datetime
from app.core.config import settings
from app.faq.logging import faq_log
from .stop import is_stop_requested
from .footer import scrape_page, scrape_footer_topics
from .embedder import store_embeddings
from .scraper_utils import save_debug_file

def run() -> None:
    scraper_urls = [u.strip() for u in settings.get("SCRAPER_URLS", "").split(",") if u.strip()]
    footer_base_url = settings.get("FOOTER_BASE_URL", "")
    footer_topics = [t.strip() for t in settings.get("FOOTER_TOPICS", "").split(",") if t.strip()]

    faq_log.info("[SCRAPER] Starting scraper run")

    seen_texts: set = set()
    all_chunks: list = []

    def add_chunks(chunks: list) -> None:
        for chunk in chunks:
            if chunk["text"] not in seen_texts:
                seen_texts.add(chunk["text"])
                all_chunks.append(chunk)

    if scraper_urls:
        faq_log.info("[SCRAPER] Scraping %d direct URL(s)", len(scraper_urls))
        for url in scraper_urls:
            if is_stop_requested():
                faq_log.warning("[SCRAPER] Stop requested — halting scraping")
                return
            add_chunks(scrape_page(url))

    if footer_base_url and footer_topics:
        faq_log.info("[SCRAPER] Scraping footer topics: %s", footer_topics)
        add_chunks(scrape_footer_topics(footer_base_url, footer_topics))

    if not all_chunks:
        faq_log.warning("[SCRAPER] No chunks extracted. Check SCRAPER_URLS or FOOTER_BASE_URL in .env")
        return

    faq_log.info("[SCRAPER] Total unique chunks: %d", len(all_chunks))
    save_debug_file(f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", {
        "timestamp": datetime.now().isoformat(),
        "total_chunks": len(all_chunks),
        "scraper_urls": scraper_urls,
        "footer_base_url": footer_base_url,
        "footer_topics": footer_topics,
        "table": settings.get("PG_FAQ_TABLE", "faq"),
        "embedding_model": settings.GEMINI_EMBEDDING_MODEL,
    })

    store_embeddings(all_chunks)
    faq_log.info("[SCRAPER] Scraping complete")


if __name__ == "__main__":
    run()
