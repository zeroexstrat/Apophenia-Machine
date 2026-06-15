"""Vector embedding infrastructure used across ingest, exhaust, and connect."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

try:
    from sentence_transformers import SentenceTransformer
except Exception:  # pragma: no cover
    SentenceTransformer = None  # type: ignore


@dataclass
class SearchResult:
    id: str
    score: float
    text: str


class EmbeddingStore:
    def __init__(self, path: str | Path, model_name: str = "all-MiniLM-L6-v2"):
        self.path = Path(path).expanduser().resolve()
        self.vector_path = self.path.with_suffix(".npy")
        self.meta_path = self.path.with_suffix(".json")
        self.model_name = model_name
        self._model = None
        self._dimension = 384
        if SentenceTransformer is not None:
            try:
                self._model = SentenceTransformer(model_name)
                self._dimension = self._model.get_sentence_embedding_dimension()
            except Exception:
                self._model = None
                self._dimension = 384
        self._ids: list[str] = []
        self._texts: dict[str, str] = {}
        self._vectors: np.ndarray | None = None
        self._dirty = False
        self._id_to_index: dict[str, int] = {}
        self.load()
        self._rebuild_index()

    @property
    def dimension(self) -> int:
        return int(self._dimension)

    def _ensure_matrix(self) -> np.ndarray:
        if self._vectors is None:
            self._vectors = np.zeros((0, self.dimension), dtype=np.float32)
        return self._vectors

    def _embed(self, texts: list[str]) -> np.ndarray:
        if self._model is None:
            # Deterministic lightweight fallback embedding.
            vectors: list[list[float]] = []
            for text in texts:
                digest = hashlib.sha256((text or "").encode("utf-8")).digest()
                values = []
                for idx in range(self.dimension):
                    chunk = digest[idx % len(digest)]
                    values.append((chunk / 255.0) - 0.5)
                vec = np.array(values, dtype=np.float32)
                norm = np.linalg.norm(vec)
                if norm:
                    vec = vec / norm
                vectors.append(vec.tolist())
            return np.array(vectors, dtype=np.float32)
        return np.array(self._model.encode(texts), dtype=np.float32)

    def embed_text(self, text: str) -> np.ndarray:
        return self._embed([text])[0]

    def add(self, item_id: str, text: str) -> None:
        self.add_batch([item_id], [text])

    def add_batch(self, ids: list[str], texts: list[str]) -> None:
        if not ids:
            return
        if len(ids) != len(texts):
            raise ValueError("ids and texts must be same length")

        self.remove_batch(set(ids))
        vectors = self._embed(texts)
        if vectors.size == 0:
            return
        matrix = self._ensure_matrix()
        self._ids.extend(ids)
        for item_id, text in zip(ids, texts):
            self._texts[item_id] = text
        self._vectors = np.vstack([matrix, vectors]) if matrix.size else vectors
        self._dirty = True
        self._rebuild_index()

    def search(self, query_text: str, top_k: int = 5) -> list[tuple[str, float]]:
        return self.search_batch([query_text], top_k=top_k)[0]

    def search_batch(self, query_texts: list[str], top_k: int = 5) -> list[list[tuple[str, float]]]:
        matrix = self._ensure_matrix()
        if not len(matrix):
            return [[] for _ in query_texts]
        qvecs = self._embed(query_texts)
        qnorm = np.linalg.norm(qvecs, axis=1, keepdims=True)
        vecnorm = np.linalg.norm(matrix, axis=1, keepdims=True)
        vecnorm[vecnorm == 0] = 1e-12
        qnorm[qnorm == 0] = 1e-12
        scores = (qvecs @ matrix.T) / (qnorm @ vecnorm.T)
        results: list[list[tuple[str, float]]] = []

        for row in scores:
            ranking = np.argsort(row)[::-1]
            selected: list[tuple[str, float]] = []
            for idx in ranking[: max(top_k, 0)]:
                selected.append((self._ids[idx], float(row[idx])))
            results.append(selected)
        return results

    def remove(self, item_id: str) -> None:
        self.remove_batch({item_id})

    def remove_batch(self, item_ids: set[str] | list[str]) -> None:
        to_remove = set(item_ids)
        if self._vectors is None or not to_remove:
            return
        keep_mask = [item_id not in to_remove for item_id in self._ids]
        if all(keep_mask):
            return
        self._ids = [id_ for id_, keep in zip(self._ids, keep_mask) if keep]
        self._vectors = self._vectors[keep_mask]
        for key in list(to_remove):
            self._texts.pop(key, None)
        self._dirty = True
        self._rebuild_index()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.vector_path.parent.mkdir(parents=True, exist_ok=True)
        self.meta_path.parent.mkdir(parents=True, exist_ok=True)
        matrix = self._ensure_matrix()
        np.save(self.vector_path, matrix)
        payload = {"ids": self._ids, "texts": self._texts, "model": self.model_name, "dimension": self.dimension}
        with open(self.meta_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        self._dirty = False

    def load(self) -> None:
        if not self.meta_path.exists() or not self.vector_path.exists():
            return
        try:
            with open(self.meta_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            ids = payload.get("ids", [])
            texts = payload.get("texts", {})
            self.model_name = payload.get("model", self.model_name)
            if not isinstance(ids, list) or not isinstance(texts, dict):
                return
            vectors = np.load(self.vector_path)
            self._ids = list(ids)
            self._texts = {str(k): str(v) for k, v in texts.items()}
            self._vectors = np.asarray(vectors, dtype=np.float32)
            self._rebuild_index()
        except Exception:
            self._ids = []
            self._texts = {}
            self._vectors = None

    def search_by_prefix(self, prefix: str, top_k: int = 20) -> list[tuple[str, float]]:
        if not self._ids:
            return []
        matrix = self._ensure_matrix()
        idxs = [i for i, item_id in enumerate(self._ids) if str(item_id).startswith(prefix)]
        if not idxs:
            return []
        scores = np.linalg.norm(matrix[idxs], axis=1)  # unit vectors for now
        ranking = np.argsort(scores)[::-1][:top_k]
        return [(self._ids[idxs[i]], float(scores[i])) for i in ranking]

    def texts_with_prefix(self, prefix: str) -> list[str]:
        return [self._texts[item_id] for item_id in self._ids if str(item_id).startswith(prefix)]

    def get_vector(self, item_id: str) -> np.ndarray | None:
        if self._vectors is None:
            return None
        idx = self._id_to_index.get(item_id)
        if idx is None:
            return None
        return self._vectors[idx]

    def has_id(self, item_id: str) -> bool:
        return item_id in self._id_to_index

    def ids_with_prefix(self, prefix: str) -> list[str]:
        return [item_id for item_id in self._ids if str(item_id).startswith(prefix)]

    def text(self, item_id: str) -> str | None:
        return self._texts.get(item_id)

    def _rebuild_index(self) -> None:
        self._id_to_index = {item_id: idx for idx, item_id in enumerate(self._ids)}

    @property
    def size(self) -> int:
        return len(self._ids)
