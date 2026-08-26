import asyncio
from google import genai
from google.genai import types
from google.oauth2 import service_account

from ...config import (
    faq_log,
    GEMINI_EMBEDDING_MODEL,
    VERTEX_PROJECT_ID, VERTEX_LOCATION, VERTEX_SERVICE_ACCOUNT_JSON,
)
from ...db import get_pg_table, get_pg_pool, get_pg_vector_dim
from ..utils.filters import is_noisy_chunk

# ──────────────────────────────────────────────
# Embedding Client
# ──────────────────────────────────────────────
embedding_client = None


def get_embedding_client() -> genai.Client:
    global embedding_client
    if embedding_client is not None:
        return embedding_client
    if VERTEX_SERVICE_ACCOUNT_JSON:
        creds = service_account.Credentials.from_service_account_file(
            VERTEX_SERVICE_ACCOUNT_JSON,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        embedding_client = genai.Client(vertexai=True, project=VERTEX_PROJECT_ID, location=VERTEX_LOCATION, credentials=creds)
    else:
        embedding_client = genai.Client(vertexai=True, project=VERTEX_PROJECT_ID, location=VERTEX_LOCATION)
    return embedding_client


# ──────────────────────────────────────────────
# Batch Embedding
# ──────────────────────────────────────────────
# Sends all texts in ONE batch request, returns list of vectors
def get_gemini_embeddings_batch(texts: list[str]) -> list[list]:
    client = get_embedding_client()
    result = client.models.embed_content(
        model=GEMINI_EMBEDDING_MODEL,
        contents=texts,
        config=types.EmbedContentConfig(output_dimensionality=3072),
    )
    return [e.values for e in result.embeddings]


async def get_embeddings_batch(texts: list[str]) -> list[list]:
    embeddings = await asyncio.to_thread(get_gemini_embeddings_batch, texts)
    expected_dim = get_pg_vector_dim()
    if expected_dim is not None:
        for emb in embeddings:
            if len(emb) != expected_dim:
                raise ValueError(f"Embedding dimension mismatch: model returned {len(emb)} but table stores {expected_dim}.")
    return embeddings


# ──────────────────────────────────────────────
# pgvector Retrieval
# ──────────────────────────────────────────────
# Queries pgvector using cosine similarity, filters low-similarity results (<0.2)
def retrieve_semantic_chunks(query_embedding: list, top_k: int) -> list:
    table = get_pg_table()
    pool = get_pg_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT chunk_text, url, 1 - (embedding <=> %s::vector) AS similarity, section
                FROM {table}
                ORDER BY embedding <=> %s::vector
                LIMIT %s;
                """,
                (query_embedding, query_embedding, top_k),
            )
            rows = cur.fetchall()
        return [
            {"text": row[0], "url": row[1], "similarity": row[2], "section": row[3] or ""}
            for row in rows
            if row[2] > 0.2 and not is_noisy_chunk(row[0])
        ]
    finally:
        pool.putconn(conn)
