import asyncio

from app.core.config import settings
from app.faq.logging import faq_log

CONTEXT_MAX_CHAR = settings.get("CONTEXT_MAX_CHAR", 10000, int)
from ...variables import SYSTEM_PROMPT
from .client import call_gemini_llm

# ──────────────────────────────────────────────
# Answer Generator
# ──────────────────────────────────────────────
# LLM2: Generates final answer using retrieved context chunks.
async def generate_answer(
    original_query: str,
    search_query: str,
    context_chunks: list,
    variations: list | None = None,
    language: str = "english",
) -> tuple[str, dict]:
    if context_chunks:
        capped, total = [], 0
        for c in context_chunks:
            text = c["text"]
            section = c.get("section", "")
            if section and not text.startswith(section):
                text = f"{section}: {text}"
            total += len(text)
            if total > CONTEXT_MAX_CHAR:
                break
            capped.append({**c, "text": text})
        context = "\n\n".join(c["text"] for c in capped)
        faq_log.debug("[CONTEXT] Built | chunks=%d | chars=%d", len(capped), len(context))
    else:
        context = ""

    lang_instruction = f"IMPORTANT: You MUST reply in {language}.\n\n" if language != "english" else ""
    query_lines = [f"Received query: {original_query}"]
    if search_query and search_query != original_query:
        query_lines.append(f"Rewritten query: {search_query}")
    if variations:
        query_lines.append("Possible queries:")
        query_lines.extend(f"- {v}" for v in variations if v)
    query_block = "\n".join(query_lines)

    user_content = (
        lang_instruction
        + f"[CONTEXT]\n{context}\n[/CONTEXT]\n\n{query_block}\n\nAnswer using ONLY the context above."
        if context else
        lang_instruction + query_block
    )

    return await asyncio.to_thread(
        call_gemini_llm,
        [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_content}],
        call_name="generate_answer",
    )
