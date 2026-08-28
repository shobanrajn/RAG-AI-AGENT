import asyncio
import json
import re

from app.faq.logging import faq_log
from ...variables import REWRITE_SYSTEM_PROMPT
from .client import call_gemini_llm, EMPTY_USAGE

# ──────────────────────────────────────────────
# Query Rewriter
# ──────────────────────────────────────────────
# LLM1: Classifies intent, rewrites query to English, generates search variations.
# Returns: {intent, search_query, language, variations}
async def rewrite_query(query: str, history: list) -> tuple[dict, dict]:
    default = {"intent": "faq", "search_query": query, "language": "english", "variations": []}

    if not history:
        history_text = ""
    else:
        lines = []
        for m in history[-6:]:
            content = m["content"][:150] if m["role"] == "assistant" else m["content"][:400]
            lines.append(f"{m['role'].upper()}: {content}")
        history_text = "\n".join(lines)                                            # history_text is variable that hold the 3 pairs of individual message converted into single string

    user_query_content = ""                                                       # user_query_content = latest query + history_text
    if history_text:
        user_query_content += f"[CONVERSATION HISTORY]\n{history_text}\n\n"
    user_query_content += f"[LATEST QUERY]\n{query}"


    try:
        raw, usage = await asyncio.to_thread(
            call_gemini_llm,
            [{"role": "system", "content": REWRITE_SYSTEM_PROMPT}, {"role": "user", "content": user_query_content}],
            call_name="rewrite_query",
        )
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
        parsed = json.loads(raw)
        return {
            "intent":       (parsed.get("intent") or "faq").strip().lower(),
            "search_query": (parsed.get("search_query") or "").strip() or query,
            "language":     (parsed.get("language") or "english").strip().lower(),
            "variations":   [v.strip() for v in (parsed.get("variations") or []) if isinstance(v, str) and v.strip()],
        }, usage
    except Exception as e:
        faq_log.warning("[REWRITE] Failed (%s: %s) — falling back to original query", type(e).__name__, e)
        return default, EMPTY_USAGE
