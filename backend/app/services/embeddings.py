"""Text embeddings for retrieval (past questions, table descriptions).

EMBEDDER=fastembed — BAAI/bge-small-en-v1.5 through ONNX, no torch. Understands
  paraphrases ("sales per area" ~ "revenue by region"). Needs ~300 MB of RAM.
EMBEDDER=hash (default) — feature-hashed words and word pairs. No model, no
  download, near-zero memory; matches questions that share wording. Used on
  small machines and in tests.

Both give unit-length 384-dim vectors, so the pgvector column doesn't change
when you switch — but stored vectors from one aren't comparable with the
other, so query_log rows remember which embedder made them.
"""
import hashlib
import logging
import os
import re
import threading
import numpy as np

log = logging.getLogger(__name__)

DIM = 384
EMBEDDER = os.getenv("EMBEDDER", "hash")
FASTEMBED_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")

class HashEmbedder:
    name = "hash"
    # cosine at or above this counts as "the same kind of question"
    min_similarity = 0.5

    def _features(self, text: str) -> list[str]:
        words = re.findall(r"[a-z0-9]+", text.lower())
        return words + [f"{a} {b}" for a, b in zip(words, words[1:])]

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), DIM), dtype=np.float32)
        for i, text in enumerate(texts):
            for f in self._features(text):
                h = int.from_bytes(hashlib.blake2b(f.encode(), digest_size=8).digest(), "little")
                out[i, h % DIM] += 1.0 if (h >> 32) & 1 else -1.0
        return _normalise(out)

class FastEmbedder:
    name = "fastembed"
    # bge scores even unrelated questions ~0.6, so the bar is higher
    min_similarity = 0.75

    def __init__(self, model: str = FASTEMBED_MODEL):
        self.model_name = model
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                from fastembed import TextEmbedding
                self._model = TextEmbedding(self.model_name)
        return self._model

    def embed(self, texts: list[str]) -> np.ndarray:
        vecs = np.array(list(self._load().embed(texts)), dtype=np.float32)
        if vecs.shape[1] != DIM:
            raise ValueError(f"{self.model_name} gives {vecs.shape[1]}-dim vectors, the schema stores {DIM}")
        return _normalise(vecs)

def _normalise(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.where(norms == 0, 1, norms)

_embedder = None

def get_embedder():
    global _embedder
    if _embedder is None:
        if EMBEDDER == "fastembed":
            _embedder = FastEmbedder()
        elif EMBEDDER == "hash":
            _embedder = HashEmbedder()
        else:
            raise ValueError(f"EMBEDDER must be 'hash' or 'fastembed', got {EMBEDDER!r}")
    return _embedder

def embed_one(text: str) -> list[float]:
    return get_embedder().embed([text])[0].tolist()
