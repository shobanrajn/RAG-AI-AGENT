import re
from app.core.config import settings

# ──────────────────────────────────────────────
# Section helpers
# ──────────────────────────────────────────────
def make_section(level: int, title: str) -> dict:
    return {"level": level, "title": title, "content": "", "subsections": []}


def flush_buffer(buffer: list, target: dict | None) -> None:
    if not buffer or target is None:
        return
    text = re.sub(r'\*{1,2}([^*]+)\*{1,2}', r'\1', " ".join(" ".join(buffer).split()))
    text = re.sub(r'\*{1,2}', "", text)
    if text:
        target["content"] = (target.get("content", "") + " " + text).strip()
    buffer.clear()


def has_content(section: dict) -> bool:
    return bool(section.get("content", "").strip()) or any(
        s.get("content", "").strip() for s in section.get("subsections", [])
    )


# ──────────────────────────────────────────────
# Heading processors
# ──────────────────────────────────────────────
def process_h1_h2(stripped: str, buffer: list, state: dict, sections: list) -> None:
    match = re.match(r'^#{1,2}\s+(.+)$', stripped)
    if not match:
        return
    flush_buffer(buffer, state["h4"] or state["h3"] or state["h2"])
    state["h2"] = make_section(2, match.group(1).strip())
    state["h3"] = state["h4"] = None
    sections.append(state["h2"])


def process_h3(stripped: str, buffer: list, state: dict) -> None:
    match = re.match(r'^###\s+(.+)$', stripped)
    if not match:
        return
    flush_buffer(buffer, state["h4"] or state["h3"] or state["h2"])
    title = match.group(1).strip()
    if re.match(r'^[\d,\.₹\+\s]{1,25}$', title) and not re.search(r'[a-zA-Z]', title):
        state["h4"] = None
        return
    state["h3"] = make_section(3, title)
    state["h4"] = None
    if state["h2"]:
        state["h2"]["subsections"].append(state["h3"])


def process_h4(stripped: str, buffer: list, state: dict) -> None:
    match = re.match(r'^####\s+(.+)$', stripped)
    if not match:
        return
    flush_buffer(buffer, state["h4"] or state["h3"] or state["h2"])
    title = re.sub(r'\*{1,2}([^*]+)\*{1,2}', r'\1', match.group(1).strip()).strip()
    if not title:
        return
    state["h4"] = make_section(4, title)
    parent = state["h3"] or state["h2"]
    if parent:
        parent["subsections"].append(state["h4"])


# ──────────────────────────────────────────────
# FAQ + paragraph fallbacks
# ──────────────────────────────────────────────
def extract_faq_pairs(markdown: str) -> list:
    subsections = []
    for match in re.finditer(r'^\*\s+(.+\?)\s*\n((?:(?!\*\s).+\n?)*)', markdown, re.MULTILINE):
        question = match.group(1).strip()
        answer = re.sub(r'\s+', " ", match.group(2).strip())
        if question and len(answer) > 20:
            subsections.append({"level": 3, "title": question, "content": answer, "subsections": []})

    for match in re.finditer(r'Q[:\.]?\s*(.+\?)\s*\n+A[:\.]?\s*(.+?)(?=\nQ[:\.]?|\Z)', markdown, re.DOTALL | re.MULTILINE):
        question = match.group(1).strip()
        answer = re.sub(r'\s+', " ", match.group(2).strip())
        if question and len(answer) > 20:
            subsections.append({"level": 3, "title": question, "content": answer, "subsections": []})
    return subsections


def extract_plain_paragraphs(markdown: str) -> str:
    paragraphs = []
    for line in markdown.split("\n"):
        stripped = line.strip()
        if re.match(r'^#+\s', stripped):
            continue
        if re.match(r'^\*\s+\S.{0,40}$', stripped) and not re.search(r'[.!?:]', stripped):
            continue
        if len(stripped) > 40:
            paragraphs.append(stripped)
    return " ".join(paragraphs)


# ──────────────────────────────────────────────
# Main parse entry
# ──────────────────────────────────────────────
def parse_sections(markdown: str) -> list:
    markdown = re.sub(r'!\[.*?\]\(.*?\)', "", markdown)
    markdown = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', markdown)
    markdown = re.sub(r'https?://\S+', "", markdown)
    markdown = re.sub(r'\n{3,}', "\n\n", markdown)

    sections: list = []
    buffer: list = []
    state = {"h2": None, "h3": None, "h4": None}

    for line in markdown.split("\n"):
        stripped = line.strip()
        if re.match(r'^#{1,2}\s', stripped) and not stripped.startswith("###"):
            process_h1_h2(stripped, buffer, state, sections)
        elif re.match(r'^###\s', stripped) and not stripped.startswith("####"):
            process_h3(stripped, buffer, state)
        elif re.match(r'^####\s', stripped):
            process_h4(stripped, buffer, state)
        elif stripped:
            buffer.append(stripped)

    flush_buffer(buffer, state["h4"] or state["h3"] or state["h2"])

    faq_sections = extract_faq_pairs(markdown)
    if faq_sections:
        sections.append({"level": 2, "title": "FAQs", "content": "", "subsections": faq_sections})

    if not sections:
        plain = extract_plain_paragraphs(markdown)
        if plain:
            sections.append({"level": 2, "title": "Content", "content": plain, "subsections": []})

    return [s for s in sections if has_content(s)]


# ──────────────────────────────────────────────
# Chunking
# ──────────────────────────────────────────────
def split_into_chunks(text: str, url: str, full_title: str, topic: str, link_text: str, seen: set) -> list:
    chunks = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if len(candidate) > settings.get("CHUNK_SIZE", 600, int):
            if current and current not in seen:
                seen.add(current)
                chunks.append({"url": url, "text": current, "section": full_title, "topic": topic, "link_text": link_text})
            current = word
        else:
            current = candidate
    if current and current not in seen:
        seen.add(current)
        chunks.append({"url": url, "text": current, "section": full_title, "topic": topic, "link_text": link_text})
    return chunks


def sections_to_chunks(sections: list, url: str, topic: str = "", link_text: str = "") -> list:
    chunks: list = []
    seen: set = set()

    def process(section: dict, parent_title: str = "") -> None:
        title = section.get("title", "")
        content = section.get("content", "")
        full_title = f"{parent_title} > {title}" if parent_title else title

        if content:
            prefix = f"[{link_text}] " if link_text else ""
            title_prefix = f"{full_title}: " if full_title else ""
            full_text = f"{prefix}{title_prefix}{content}"
            chunks.extend(split_into_chunks(full_text, url, full_title, topic, link_text, seen))

        for sub in section.get("subsections", []):
            process(sub, full_title)

    for s in sections:
        process(s)
    return chunks
