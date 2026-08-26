import re

# ──────────────────────────────────────────────
# Chunk Noise Filter
# ──────────────────────────────────────────────
_NOISE_PATTERNS = re.compile(r'^News\s*&\s*Press Releases', re.IGNORECASE)


def is_noisy_chunk(text: str) -> bool:
    if bool(_NOISE_PATTERNS.match(text.strip())):
        return True
    text_lower = text.lower()
    return text_lower.startswith("cholamandalam securities") or text_lower.startswith("csec")
