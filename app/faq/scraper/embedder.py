from google import genai
from google.genai import types
from google.oauth2 import service_account
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.config import settings
from app.faq.logging import faq_log
from app.db.faq_chat_pg import store_chunks
from .stop import is_stop_requested


def _build_genai_client() -> genai.Client:
    if settings.get("VERTEX_SERVICE_ACCOUNT_JSON", ""):
        creds = service_account.Credentials.from_service_account_file(
            settings.VERTEX_SERVICE_ACCOUNT_JSON,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        return genai.Client(vertexai=True, project=settings.VERTEX_PROJECT_ID, location=settings.VERTEX_LOCATION, credentials=creds)
    return genai.Client(vertexai=True, project=settings.VERTEX_PROJECT_ID, location=settings.VERTEX_LOCATION)


@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
)
def get_embedding(text: str) -> tuple[list, int]:
    client = _build_genai_client()
    result = client.models.embed_content(
        model=settings.GEMINI_EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(output_dimensionality=3072),
    )
    token_count = client.models.count_tokens(model=settings.GEMINI_MODEL, contents=text).total_tokens or 0
    return result.embeddings[0].values, token_count


def store_embeddings(all_chunks: list) -> None:
    faq_log.info("[SCRAPER] Embedding %d chunks...", len(all_chunks))
    total_tokens = 0
    embedded = []
    for i, chunk in enumerate(all_chunks, 1):
        if is_stop_requested():
            faq_log.warning("[SCRAPER] Stop requested — halting at chunk %d/%d", i, len(all_chunks))
            break
        embedding, tokens = get_embedding(chunk["text"])
        total_tokens += tokens
        embedded.append({**chunk, "embedding": embedding})
        faq_log.info("[SCRAPER] [%d/%d] embedded | tokens_so_far=%d", i, len(all_chunks), total_tokens)

    store_chunks(embedded)
    faq_log.info("[SCRAPER] Embedding token usage | chunks=%d | total_tokens=%d", len(embedded), total_tokens)
    print(f"\n[SCRAPER] Total chunks embedded : {len(embedded)}")
    print(f"[SCRAPER] Total tokens used     : {total_tokens}")
