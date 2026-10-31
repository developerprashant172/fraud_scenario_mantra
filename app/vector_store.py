import os
import json
import logging
import numpy as np

logger = logging.getLogger(__name__)

class LocalVectorStore:
    """
    Ultra-fast in-memory vector store for pre-indexed scenarios.
    Executes cosine similarity search in ~1-2 milliseconds without network round-trips.
    """
    def __init__(self, cache_path: str = "fraud_scenarios_cache.json"):
        self.cache_path = cache_path
        self.scenarios = []
        self.vectors = None
        self.norms = None
        self.load()

    def load(self):
        if not os.path.exists(self.cache_path):
            logger.warning(f"Cache file {self.cache_path} not found. In-memory search will be disabled until built.")
            return False

        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                self.scenarios = json.load(f)

            raw_vectors = [s["vector"] for s in self.scenarios if "vector" in s]
            self.vectors = np.array(raw_vectors, dtype=np.float32)
            
            # Precompute L2 norms for cosine similarity
            self.norms = np.linalg.norm(self.vectors, axis=1)
            # Prevent division by zero
            self.norms[self.norms == 0] = 1e-10

            logger.info(f"Loaded {len(self.scenarios)} scenarios into in-memory vector index.")
            return True
        except Exception as e:
            logger.error(f"Failed to load vector cache from {self.cache_path}: {e}")
            return False

    def is_ready(self) -> bool:
        return self.vectors is not None and len(self.vectors) > 0

    def search(self, query_vector: list, top_k: int = 5) -> list:
        """
        In-memory cosine similarity search.
        Returns results in the exact same format as zilliz_search.
        """
        if not self.is_ready():
            return []

        q = np.array(query_vector, dtype=np.float32)
        q_norm = np.linalg.norm(q)
        if q_norm == 0:
            q_norm = 1e-10

        # Cosine similarity: (A . B) / (||A|| * ||B||)
        scores = np.dot(self.vectors, q) / (self.norms * q_norm)
        
        # Get top-k indices
        top_k = min(top_k, len(scores))
        top_indices = np.argsort(scores)[::-1][:top_k]

        formatted = []
        for idx in top_indices:
            s = self.scenarios[idx]
            sim = round(float(scores[idx]), 4)
            formatted.append({
                "id": str(s.get("id", idx)),
                "similarity": sim,
                "metadata": s.get("metadata", {})
            })

        return formatted

# Global singleton instance
fraud_vector_store = LocalVectorStore()

