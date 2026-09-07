from datetime import datetime, timezone

from app.db.session import get_faq_token_db
from app.faq.logging import faq_log


def _get_col():
    return get_faq_token_db()


async def save_faq_token_usage(
    session_id: str,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
    thinking_tokens: int = 0,
) -> None:
    try:
        now          = datetime.now(timezone.utc)
        is_cache_hit = cached_tokens > 0
        billable_in  = input_tokens - cached_tokens

        pipeline = [
            # Step 1: increment all counters atomically
            {"$set": {
                "session_id":              session_id,
                "query_count":             {"$add": [{"$ifNull": ["$query_count", 0]}, 1]},
                "io_tokens.total_input":   {"$add": [{"$ifNull": ["$io_tokens.total_input", 0]},  billable_in]},
                "io_tokens.total_output":  {"$add": [{"$ifNull": ["$io_tokens.total_output", 0]}, output_tokens]},
                "cache_tokens.cache_hits": {"$add": [{"$ifNull": ["$cache_tokens.cache_hits", 0]}, 1 if is_cache_hit else 0]},
                "cache_tokens.total_tokens_read": {
                    "$add": [{"$ifNull": ["$cache_tokens.total_tokens_read", 0]}, cached_tokens if is_cache_hit else 0]
                },
                "cache_tokens.storage_cache": {
                    "$ifNull": ["$cache_tokens.storage_cache", cached_tokens]
                },
                "thinking_tokens": {"$add": [{"$ifNull": ["$thinking_tokens", 0]}, thinking_tokens]},
                "updated_at": now,
                "created_at": {"$ifNull": ["$created_at", now]},
            }},
            # Step 2: compute averages and ratio from the already-incremented values
            {"$set": {
                "avg.input":  {"$round": [{"$divide": ["$io_tokens.total_input",  "$query_count"]}, 2]},
                "avg.output": {"$round": [{"$divide": ["$io_tokens.total_output", "$query_count"]}, 2]},
                "ratio": {"$cond": [
                    {"$gt": ["$io_tokens.total_output", 0]},
                    {"$round": [{"$divide": ["$io_tokens.total_input", "$io_tokens.total_output"]}, 4]},
                    0.0,
                ]},
            }},
        ]

        result = await _get_col().update_one(
            {"session_id": session_id},
            pipeline,
            upsert=True,
        )
        action = "inserted" if result.upserted_id else "updated"
        faq_log.info(
            "[MONGO TOKEN] %s | session=%s | billable_in=%d out=%d cached=%d hit=%s thinking=%d",
            action, session_id, billable_in, output_tokens, cached_tokens, is_cache_hit, thinking_tokens,
        )
    except Exception as e:
        faq_log.error("[MONGO TOKEN] Failed to save token usage: %s", e)
