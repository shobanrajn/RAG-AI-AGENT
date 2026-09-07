import asyncio
import time

from app.core.exceptions import AppException
from app.core.config import settings
from app.faq.logging import faq_log
from app.db.faq_chat_pg import save_message, get_history
from app.db.faq_token_mongo import save_faq_token_usage
from .utils.token import log_token_usage, usage_count
from .retrieval import get_embeddings_batch, retrieve_semantic_chunks, merge_and_rerank
from .llm import rewrite_query, generate_answer

TOP_K = settings.get("TOP_K", 40, int)

async def invoke_faq_agent(
    query: str,
    session_id: str,
    history: list = None,
) -> dict:
    # main : User Query → History → Rewrite → Embed → Retrieve → Deduplicate → Rerank → Generate Answer → Save History → Return Response
    faq_log.info("="*100)
    faq_log.info(f"[SESSION: {session_id}] RECEIVED QUERY: {query}")

    try:

        # Auto-fetch history from DB and rewrite query in parallel
        norm_history = history if history is not None else get_history(session_id)

        # Step 1: Rewrite query
        rewrite_start = time.perf_counter()
        rewritten, rewrite_usage = await rewrite_query(query, norm_history)
        rewrite_elapsed = time.perf_counter() - rewrite_start
        faq_log.debug(
            "[SESSION: %s] QUERY REWRITE | elapsed=%.2fs | search_query=%r",
            session_id, rewrite_elapsed,
            rewritten.get("search_query"),
        )

        search_query = rewritten.get("search_query") or query
        language     = rewritten.get("language", "english")
        variations   = rewritten.get("variations") or []
        intent       = rewritten.get("intent", "faq")

        # Short-circuit: no retrieval or LLM2 needed for greetings/acknowledgements
        if intent in ("greeting", "acknowledgement"):
            answer, answer_usage = await generate_answer(
                original_query=query,
                search_query="",
                variations=[],
                context_chunks=[],
                language=language,
            )
            save_message(session_id, "user", query)
            save_message(session_id, "assistant", answer)
            faq_log.info(f"[SESSION: {session_id}] {intent.upper()} SHORT-CIRCUIT (lang={language})")
            log_token_usage(session_id, intent, rewrite_usage, answer_usage, elapsed_s=rewrite_elapsed)
            try:
                await save_faq_token_usage(
                    session_id,
                    usage_count(rewrite_usage, "promptTokenCount") + usage_count(answer_usage, "promptTokenCount"),
                    usage_count(rewrite_usage, "candidatesTokenCount") + usage_count(answer_usage, "candidatesTokenCount"),
                    cached_tokens=usage_count(answer_usage, "cachedContentTokenCount"),
                    thinking_tokens=usage_count(rewrite_usage, "thoughtsTokenCount") + usage_count(answer_usage, "thoughtsTokenCount"),
                )
            except Exception:
                pass
            return {"result_text": answer, "label": "Rag-Agent"}

        # Step 2: Multi-Query + Embed + Retrieve
        all_queries = []
        for candidate_query in [search_query] + variations:      
            if candidate_query and candidate_query not in all_queries:
                all_queries.append(candidate_query)
        faq_log.debug(f"[SESSION: {session_id}]   queries={all_queries}")

        # Run all embeddings in ONE batch API call
        embed_start = time.perf_counter()
        embeddings = await get_embeddings_batch(all_queries)
        faq_log.debug("[SESSION: %s] EMBEDDINGS DONE | queries=%d | elapsed=%.2fs", session_id, len(all_queries), time.perf_counter() - embed_start)

        faq_log.debug(f"[SESSION: {session_id}] RETRIEVAL")
        retrieval_start = time.perf_counter()
        chunk_lists = await asyncio.gather(
            *[asyncio.to_thread(retrieve_semantic_chunks, emb, TOP_K) for emb in embeddings]
        )
        faq_log.debug("[SESSION: %s] RETRIEVAL DONE | elapsed=%.2fs", session_id, time.perf_counter() - retrieval_start)
        seen_texts = set()
        all_chunks = []
        for chunks in chunk_lists:
            for chunk in chunks:
                if chunk["text"] not in seen_texts:
                    seen_texts.add(chunk["text"])
                    all_chunks.append(chunk)

        faq_log.debug(f"[SESSION: {session_id}]   Semantic (deduped): {len(all_chunks)}")
        ranked_chunks = await asyncio.to_thread(merge_and_rerank, all_chunks, search_query)

        faq_log.debug(f"[SESSION: {session_id}]   Final chunks: {len(ranked_chunks)}")
        for index, chunk in enumerate(ranked_chunks):
            faq_log.debug(
                "[SESSION: %s]   chunk[%d/%d] section=%r sim=%.3f rerank=%.3f | %r",
                session_id, index + 1, len(ranked_chunks),
                chunk.get("section", ""), chunk.get("similarity", 0.0),
                chunk.get("rerank_score", 0.0), chunk["text"][:150].replace("\n", " "),
            )

        if not ranked_chunks:
            faq_log.warning(f"[SESSION: {session_id}] NO CHUNKS FOUND")
            return {"result_text": "Sorry, I do not have any information about that topic.", "label": "Rag-Agent"}

        # Step 3: Generate answer
        faq_log.debug("[SESSION: %s] LLM QUERY SNAPSHOT | original=%r | all_queries=%s", session_id, search_query, all_queries)
        llm_start = time.perf_counter()

        answer, answer_usage = await generate_answer(
            original_query=query,
            search_query=search_query,
            variations=variations,
            context_chunks=ranked_chunks,
            language=language,
        )

        llm_elapsed = time.perf_counter() - llm_start

        # ── Real token summary for this session request ──
        rewrite_prompt    = usage_count(rewrite_usage, "promptTokenCount")
        rewrite_output    = usage_count(rewrite_usage, "candidatesTokenCount")
        answer_prompt     = usage_count(answer_usage, "promptTokenCount")
        answer_output     = usage_count(answer_usage, "candidatesTokenCount")
        cached_tokens     = usage_count(answer_usage, "cachedContentTokenCount")
        thinking_tokens   = usage_count(rewrite_usage, "thoughtsTokenCount") + usage_count(answer_usage, "thoughtsTokenCount")
        total_input       = rewrite_prompt + answer_prompt
        total_output      = rewrite_output + answer_output
        grand_total       = total_input + total_output

        faq_log.info(
            "[SESSION: %s] TOKEN USAGE | "
            "rewrite=(%d in / %d out) | "
            "answer=(%d in / %d out, cached=%s) | "
            "thinking=%d | "
            "TOTAL input=%d output=%d grand=%d | "
            "elapsed=%.2fs",
            session_id,
            rewrite_prompt, rewrite_output,
            answer_prompt, answer_output, cached_tokens,
            thinking_tokens,
            total_input, total_output, grand_total,
            llm_elapsed,
        )

        faq_log.info(f"[SESSION: {session_id}] ANSWER GENERATED: {answer}")

        faq_log.debug(f"[SESSION: {session_id}] SAVING TO DATABASE...")
        save_message(session_id, "user", query)
        save_message(session_id, "assistant", answer)

        log_token_usage(session_id, intent, rewrite_usage, answer_usage, llm_elapsed)
        try:
            await save_faq_token_usage(session_id, total_input, total_output, cached_tokens=cached_tokens, thinking_tokens=thinking_tokens)
        except Exception:
            pass

        faq_log.info(f"[SESSION: {session_id}] RESPONSE COMPLETE - Status: 200")
        faq_log.info("=" * 100)
        return {"result_text": answer, "label": "Rag-Agent"}

    except Exception as e:
        faq_log.error(f"[SESSION: {session_id}] ERROR: {type(e).__name__}: {str(e)}", exc_info=True)
        faq_log.error("=" * 100)
        raise AppException("We ran into a technical issue. Please try again later.", status_code=500)
