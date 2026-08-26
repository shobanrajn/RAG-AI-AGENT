import os
import spacy
from dotenv import load_dotenv

IS_SCRAPER = os.path.basename(__import__('__main__').__file__ or '') == 'scraper.py' if hasattr(__import__('__main__'), '__file__') else False

# Loads .env from project root (two levels up from app/faq/)
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env"), override=True)

# ──────────────────────────────────────────────
# Env Config
# ──────────────────────────────────────────────
PG_HOST      = os.getenv("PG_HOST")
PG_PORT      = os.getenv("PG_PORT")
PG_DB        = os.getenv("PG_DB")
PG_USER      = os.getenv("PG_USER")
PG_PASSWORD  = os.getenv("PG_PASSWORD")
GEMINI_EMBEDDING_MODEL     = os.getenv("GEMINI_EMBEDDING_MODEL")
VERTEX_RERANKER_MODEL      = os.getenv("VERTEX_RERANKER_MODEL")
RERANKER_PATH          = os.getenv("RERANKER_PATH")
GEMINI_MODEL               = (os.getenv("GEMINI_MODEL") or "").strip()
VERTEX_PROJECT_ID          = (os.getenv("VERTEX_PROJECT_ID") or "").strip()
VERTEX_LOCATION            = (os.getenv("VERTEX_LOCATION") or "").strip()
VERTEX_SERVICE_ACCOUNT_JSON = (os.getenv("VERTEX_SERVICE_ACCOUNT_JSON") or "").strip()
SCRAPER_URLS    = [u.strip() for u in (os.getenv("SCRAPER_URLS") or "").split(",") if u.strip()]
FOOTER_BASE_URL = os.getenv("FOOTER_BASE_URL", "")
FOOTER_TOPICS   = [t.strip() for t in (os.getenv("FOOTER_TOPICS") or "").split(",") if t.strip()]

PG_FAQ_TABLE  = os.getenv("PG_FAQ_TABLE", "faq")
PG_CHAT_TABLE = os.getenv("PG_CHAT_TABLE", "chat_history")
TOP_K                  = int(os.getenv("TOP_K", "40"))
CHUNK_SIZE             = int(os.getenv("CHUNK_SIZE", "600"))
RERANK_SCORE_THRESHOLD = float(os.getenv("RERANK_SCORE_THRESHOLD", "-1.0"))
RERANK_POOL_SIZE       = int(os.getenv("RERANK_POOL_SIZE", "40"))
CONTEXT_MAX_CHAR   = int(os.getenv("CONTEXT_MAX_CHAR", "10000"))
DEBUG_MODE    = os.getenv("DEBUG_MODE", "false").lower() == "true"
DEBUG_DIR     = os.getenv("DEBUG_DIR", "./scraper_debug")

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
    from .db import ensure_chat_table
    ensure_chat_table()
