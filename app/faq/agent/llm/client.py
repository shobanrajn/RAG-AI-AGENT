import time
from google import genai
from google.genai import types
from google.oauth2 import service_account

from ...config import (
    faq_log,
    GEMINI_MODEL,
    VERTEX_PROJECT_ID, VERTEX_LOCATION, VERTEX_SERVICE_ACCOUNT_JSON,
)
from ...variables import SYSTEM_PROMPT

# ──────────────────────────────────────────────
# Gemini Client
# ──────────────────────────────────────────────
def get_genai_client() -> genai.Client:
    if VERTEX_SERVICE_ACCOUNT_JSON:
        creds = service_account.Credentials.from_service_account_file(
            VERTEX_SERVICE_ACCOUNT_JSON,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        return genai.Client(vertexai=True, project=VERTEX_PROJECT_ID, location=VERTEX_LOCATION, credentials=creds)
    return genai.Client(vertexai=True, project=VERTEX_PROJECT_ID, location=VERTEX_LOCATION)


# ──────────────────────────────────────────────
# System Prompt Cache
# ──────────────────────────────────────────────
answer_cache_name: str | None = None
answer_cache_expires: float = 0.0
CACHE_TTL_SECONDS = 3600


def get_answer_cache(client) -> str | None:
    global answer_cache_name, answer_cache_expires
    now = time.time()
    if answer_cache_name and now < answer_cache_expires:
        faq_log.info("[CACHE] System prompt cache HIT | name=%s | expires_in=%.0fs", answer_cache_name, answer_cache_expires - now)
        return answer_cache_name
    try:
        cached = client.caches.create(
            model=GEMINI_MODEL,
            config=types.CreateCachedContentConfig(
                system_instruction=SYSTEM_PROMPT,
                ttl=f"{CACHE_TTL_SECONDS}s",
            ),
        )
        answer_cache_name = cached.name
        answer_cache_expires = now + CACHE_TTL_SECONDS - 60
        faq_log.info("[CACHE] System prompt cached | name=%s | ttl=%ds", answer_cache_name, CACHE_TTL_SECONDS)
        return answer_cache_name
    except Exception as e:
        faq_log.warning("[CACHE] Failed to create cache (%s) — using inline system prompt", e)
        return None


# ──────────────────────────────────────────────
# Core Gemini Call
# ──────────────────────────────────────────────
EMPTY_USAGE: dict = {"promptTokenCount": 0, "candidatesTokenCount": 0, "totalTokenCount": 0, "cachedContentTokenCount": 0}


def call_gemini_llm(messages: list, max_tokens: int = 8192, call_name: str = "unknown") -> tuple[str, dict]:
    system_text = "\n\n".join(
        m.get("content", "") for m in messages
        if m.get("role") == "system" and m.get("content")
    )
    contents = []
    for message in messages:
        role    = message.get("role")
        content = message.get("content", "")
        if role == "system" or not content:
            continue
        contents.append(types.Content(
            role="model" if role == "assistant" else "user",
            parts=[types.Part(text=content)],
        ))

    if not contents:
        raise ValueError("At least one non-system message is required.")

    started_at = time.perf_counter()
    try:
        client = get_genai_client()
        cache_name = get_answer_cache(client) if call_name == "generate_answer" else None
        faq_log.debug("[GEMINI] Cache ready | call=%s | cache=%s", call_name, cache_name or "none")
        config = types.GenerateContentConfig(
            temperature=0.1,
            max_output_tokens=max_tokens,
            stop_sequences=["\n\nQuestion:", "\nQuestion:", "Q:", "\n\nAnswer:"],
            cached_content=cache_name if cache_name else None,
            system_instruction=None if cache_name else (system_text or None),
            labels={"agent": "rag-agent"},
        )
        response = client.models.generate_content(model=GEMINI_MODEL, contents=contents, config=config)
        elapsed = time.perf_counter() - started_at
        content = response.text.strip() if response.text else ""
        um = response.usage_metadata
        usage = {
            "promptTokenCount":        getattr(um, "prompt_token_count", 0) or 0,
            "candidatesTokenCount":    getattr(um, "candidates_token_count", 0) or 0,
            "totalTokenCount":         getattr(um, "total_token_count", 0) or 0,
            "cachedContentTokenCount": getattr(um, "cached_content_token_count", 0) or 0,
        }
        finish_reason = response.candidates[0].finish_reason.name if response.candidates else "n/a"
        faq_log.debug(
            "[GEMINI] RESPONSE | call=%s | wall=%.2fs | finish=%s | prompt=%s | output=%s | cached=%s",
            call_name, elapsed, finish_reason,
            usage.get("promptTokenCount"), usage.get("candidatesTokenCount"), usage.get("cachedContentTokenCount"),
        )
        return content or "Sorry, I could not generate a response right now.", usage
    except Exception as e:
        faq_log.error("[GENAI] Error: %s: %s", type(e).__name__, e)
        return "We are receiving too many AI requests right now. Please try again in a minute.", EMPTY_USAGE
