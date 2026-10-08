"""Embedding model, loaded once per process. Same model as the seed used for product descriptions."""
from functools import lru_cache

from app.config import get_settings

QUERY_PREFIX = "Represent this sentence for searching relevant passages: "  # bge query instruction


@lru_cache
def _model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(get_settings().EMBED_MODEL)


def embed_query(text: str) -> list[float]:
    return _model().encode(QUERY_PREFIX + text, normalize_embeddings=True).tolist()
