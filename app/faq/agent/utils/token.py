import json
import time
from collections import defaultdict
from pathlib import Path

from app.faq.logging import token_log, get_log_dir as _get_log_dir

# ──────────────────────────────────────────────
# Token Usage Logging
# ──────────────────────────────────────────────
_daily_totals: dict = defaultdict(lambda: {
    "rewrite_in": 0, "rewrite_out": 0,
    "answer_in": 0, "answer_out": 0,
    "cached": 0, "grand_total": 0,
})
_daily_totals_loaded: set = set()


def usage_count(usage: dict, key: str) -> int:
    return int((usage or {}).get(key, 0) or 0)


def _load_daily_totals(today: str) -> None:
    if today in _daily_totals_loaded:
        return
    _daily_totals_loaded.add(today)
    log_path = Path(_get_log_dir()) / f"faq_token_usage_{today}.log"
    if not log_path.exists():
        return
    try:
        with open(log_path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if e.get("date") != today:
                    continue
                for key in ("rewrite_in", "rewrite_out", "answer_in", "answer_out", "cached", "grand_total"):
                    _daily_totals[today][key] += e.get(key, 0)
    except Exception:
        pass


def log_token_usage(
    session_id: str,
    intent: str,
    rewrite_usage: dict,
    answer_usage: dict | None = None,
    elapsed_s: float = 0.0,
) -> None:
    answer_usage   = answer_usage or {}
    rewrite_prompt = usage_count(rewrite_usage, "promptTokenCount")
    rewrite_output = usage_count(rewrite_usage, "candidatesTokenCount")
    answer_prompt  = usage_count(answer_usage, "promptTokenCount")
    answer_output  = usage_count(answer_usage, "candidatesTokenCount")
    cached_tokens  = usage_count(answer_usage, "cachedContentTokenCount")
    total_input    = rewrite_prompt + answer_prompt
    total_output   = rewrite_output + answer_output
    grand_total    = total_input + total_output

    today = time.strftime("%Y-%m-%d")
    _load_daily_totals(today)
    _daily_totals[today]["rewrite_in"]  += rewrite_prompt
    _daily_totals[today]["rewrite_out"] += rewrite_output
    _daily_totals[today]["answer_in"]   += answer_prompt
    _daily_totals[today]["answer_out"]  += answer_output
    _daily_totals[today]["cached"]      += cached_tokens
    _daily_totals[today]["grand_total"] += grand_total
    d = _daily_totals[today]

    token_log.info(json.dumps({
        "date":            today,
        "time":            time.strftime("%H:%M:%S"),
        "session_id":      session_id,
        "intent":          intent,
        "rewrite_in":      rewrite_prompt,
        "rewrite_out":     rewrite_output,
        "answer_in":       answer_prompt,
        "answer_out":      answer_output,
        "cached":          cached_tokens,
        "total_in":        total_input,
        "total_out":       total_output,
        "grand_total":     grand_total,
        "elapsed_s":       round(elapsed_s, 2),
        "day_rewrite_in":  d["rewrite_in"],
        "day_rewrite_out": d["rewrite_out"],
        "day_answer_in":   d["answer_in"],
        "day_answer_out":  d["answer_out"],
        "day_cached":      d["cached"],
        "day_grand_total": d["grand_total"],
    }, ensure_ascii=False))
