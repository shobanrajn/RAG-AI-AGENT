from datetime import datetime, timezone

from app.db.session import mongo_client
from app.core.config import settings
from app.faq.logging import faq_log


def _get_col():
    db = mongo_client[settings.MONGO_DB_NAME]
    return db[settings.MONGO_FAQ_TOKEN_COLLECTION]


async def save_faq_token_usage(
    session_id: str,
    input_tokens: int,
    output_tokens: int,
) -> None:
    try:
        now = datetime.now(timezone.utc)
        total_tokens = input_tokens + output_tokens
        io_ratio = round(input_tokens / output_tokens, 4) if output_tokens else 0.0

        await _get_col().update_one(
            {"session_id": session_id},
            {
                "$inc": {
                    "input_tokens":  input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens":  total_tokens,
                    "query_count":   1,
                },
                "$set": {
                    "io_ratio":   io_ratio,
                    "week":       f"{now.isocalendar().year}-W{now.isocalendar().week:02d}",
                    "month":      now.strftime("%Y-%m"),
                    "date":       now.strftime("%Y-%m-%d"),
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
    except Exception as e:
        faq_log.error("[MONGO TOKEN] Failed to save token usage: %s", e)
