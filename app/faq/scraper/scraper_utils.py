import os
import json
import hashlib
from urllib.parse import urlparse

from app.core.config import settings
from app.faq.logging import faq_log

SKIP_EXTENSIONS = (".pdf", ".jpg", ".png", ".svg", ".mp4", ".zip")


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:8]


def is_scrapable_url(url: str, base_url: str) -> bool:
    parsed = urlparse(url)
    base_domain = urlparse(base_url).netloc
    if parsed.netloc and parsed.netloc != base_domain:
        return False
    if any(url.lower().endswith(ext) for ext in SKIP_EXTENSIONS):
        return False
    return url.startswith("http")


def save_debug_file(filename: str, content) -> None:
    if not settings.get("DEBUG_MODE", "false").lower() == "true":
        return
    debug_dir = os.path.realpath(settings.get("DEBUG_DIR", "./scraper_debug"))
    os.makedirs(debug_dir, exist_ok=True)
    filepath = os.path.join(debug_dir, os.path.basename(filename))
    with open(filepath, "w", encoding="utf-8") as f:
        if isinstance(content, (dict, list)):
            json.dump(content, f, indent=2, ensure_ascii=False)
        else:
            f.write(content)
    faq_log.debug("[SCRAPER] Saved debug file: %s", filename)
