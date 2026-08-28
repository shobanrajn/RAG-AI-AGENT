import os
import spacy
from dotenv import load_dotenv

# Explicit .env path — needed when scraper runs as standalone script
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env"), override=True)

IS_SCRAPER = os.path.basename(__import__('__main__').__file__ or '') == 'scraper.py' if hasattr(__import__('__main__'), '__file__') else False

# ──────────────────────────────────────────────
# Spacy Singleton
# ──────────────────────────────────────────────
_nlp = None


def get_nlp():
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("en_core_web_sm", disable=["parser", "ner"])
    return _nlp


if not IS_SCRAPER:
    from app.db.faq_chat_pg import ensure_chat_table
    ensure_chat_table()
