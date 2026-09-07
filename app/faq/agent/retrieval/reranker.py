import math
from sentence_transformers import CrossEncoder

from app.core.config import settings
from app.faq.logging import faq_log
from app.faq.setup import get_nlp

# ──────────────────────────────────────────────
# MS-Marco Reranker
# ──────────────────────────────────────────────
reranker = None


def load_reranker() -> CrossEncoder:
    global reranker
    if reranker is not None:
        return reranker
    reranker = CrossEncoder(settings.RERANKER_PATH, local_files_only=True)
    faq_log.info("[RERANKER] MS-Marco reranker loaded from %s", settings.RERANKER_PATH)
    return reranker


def rerank(query: str, chunks: list, top_k: int) -> list:
    if not chunks:
        return []
    try:
        global reranker
        pairs = [(query, c["text"]) for c in chunks]     
        scores = reranker.predict(pairs)
        for i, chunk in enumerate(chunks):
            chunk["rerank_score"] = float(scores[i])     
        ranked   = sorted(chunks, key=lambda x: x["rerank_score"], reverse=True)
        filtered = [c for c in ranked if c["rerank_score"] >= settings.get("RERANK_SCORE_THRESHOLD", -1.0, float)]
        faq_log.debug("[RERANKER] threshold=%.2f | before=%d | after=%d", settings.get("RERANK_SCORE_THRESHOLD", -1.0, float), len(ranked), len(filtered))
        return filtered[:top_k]
    except Exception as e:
        faq_log.warning("[RERANKER] Reranker failed (%s) — falling back to RRF order", e)
        for chunk in chunks:
            chunk["rerank_score"] = 0.0
        return chunks[:top_k]


# ──────────────────────────────────────────────
# BM25
# ──────────────────────────────────────────────
def tokenize(text: str) -> list:
    doc = get_nlp()(text.lower())
    return [token.lemma_ for token in doc if not token.is_punct and not token.is_space]


def bm25_score(query_tokens, doc_tokens, df, n_docs, avgdl, k1=1.5, b=0.75) -> float:
    score, dl = 0.0, len(doc_tokens)
    tf_map = {}
    for t in doc_tokens:
        tf_map[t] = tf_map.get(t, 0) + 1
    for t in query_tokens:
        if t not in tf_map:
            continue
        tf  = tf_map[t]
        idf = math.log((n_docs - df.get(t, 0) + 0.5) / (df.get(t, 0) + 0.5) + 1)
        score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / max(avgdl, 1)))
    return score


def bm25_rerank(query: str, chunks: list) -> list:
    if not chunks:
        return []
    corpus    = [c["text"] for c in chunks]
    df        = {}
    total_len = 0
    tokenized = []
    for doc in corpus:
        tokens = tokenize(doc)
        tokenized.append(tokens)
        total_len += len(tokens)
        for t in set(tokens):
            df[t] = df.get(t, 0) + 1
    avgdl   = total_len / max(len(corpus), 1)
    q_tokens = tokenize(query)
    for i, doc_tokens in enumerate(tokenized):
        chunks[i]["bm25_score"] = bm25_score(q_tokens, doc_tokens, df, len(corpus), avgdl)
    return chunks


# ──────────────────────────────────────────────
# Merge + Rerank (semantic → BM25 RRF → MS-Marco)
# ──────────────────────────────────────────────
def merge_and_rerank(semantic: list, query: str) -> list:
    if not semantic:
        return []
    candidates = bm25_rerank(query, [dict(c) for c in semantic])

    sem_rank  = {c["text"]: i for i, c in enumerate(semantic)}
    bm25_rank = {c["text"]: i for i, c in enumerate(sorted(candidates, key=lambda c: c.get("bm25_score", 0), reverse=True))}

    for c in candidates:
        t = c["text"]
        c["rrf_score"] = 0.7 * (1 / (60 + sem_rank.get(t, len(candidates)))) + 0.3 * (1 / (60 + bm25_rank.get(t, len(candidates))))

    fused = sorted(candidates, key=lambda c: c["rrf_score"], reverse=True)
    top   = fused[:min(settings.get("RERANK_POOL_SIZE", 40, int), len(fused))]
    return rerank(query, top, top_k=len(top))
