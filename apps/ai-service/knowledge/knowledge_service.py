import os
import json
import time
import uuid
import logging
from typing import Optional

import numpy as np

from .markdown_loader import MarkdownLoader

logger = logging.getLogger(__name__)

# Singleton embedding model (lazy loaded)
_embedder = None
_embedder_available = False


def _ensure_embedder() -> bool:
    global _embedder, _embedder_available
    if _embedder_available:
        return True
    try:
        from sentence_transformers import SentenceTransformer
        model_name = os.getenv(
            "RAG_EMBEDDING_MODEL",
            "paraphrase-multilingual-MiniLM-L12-v2"
        )
        _embedder = SentenceTransformer(model_name)
        _embedder_available = True
        logger.info("embedding model loaded: %s", model_name)
        return True
    except Exception as exc:
        logger.warning("sentence-transformers unavailable: %s", exc)
        _embedder_available = False
        return False


class KnowledgeService:
    """RAG knowledge service: load → chunk → embed → index → search → cite.

    Manages the full ingestion and retrieval pipeline for the AiwearRag
    fashion knowledge base.

    Usage::

        svc = KnowledgeService("D:/obsidian/笔记/AiwearRag知识库")
        svc.build_index()
        results = svc.search("户外婚礼女生下雨穿什么", gender="female", top_k=5)
    """

    def __init__(self, knowledge_dir: str, index_path: Optional[str] = None):
        self.knowledge_dir = knowledge_dir
        self.index_path = index_path or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "faiss_index", "knowledge"
        )
        self._chunks: list[dict] = []
        self._index = None
        self._dimension = 0
        self._id_to_chunk: dict[int, dict] = {}
        self._build_id: str = ""
        self._embedding_model: str = ""
        self._build_created_at: str = ""
        self._build_duration_ms: int = 0

    # ---- ingestion ----

    def build_index(self, force: bool = False) -> int:
        """Load markdown files, embed, and store to FAISS index.

        Returns number of chunks indexed.
        """
        t0 = time.time()
        os.makedirs(self.index_path, exist_ok=True)

        loader = MarkdownLoader(self.knowledge_dir)
        self._chunks = loader.load_all()
        logger.info("loaded %d chunks from %d files", len(self._chunks),
                     len({c["metadata"]["file"] for c in self._chunks}))

        if not self._chunks:
            logger.warning("no chunks to index")
            return 0

        texts = [c["content"] for c in self._chunks]

        if not _ensure_embedder():
            raise RuntimeError("embedding model not available")

        self._embedding_model = os.getenv("RAG_EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
        vectors = _embedder.encode(texts, show_progress_bar=True, normalize_embeddings=True)
        self._dimension = vectors.shape[1]
        self._build_faiss(vectors)
        self._build_id = str(uuid.uuid4())[:8]
        self._build_created_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        self._build_duration_ms = int((time.time() - t0) * 1000)
        self._save_index()
        return len(self._chunks)

    def _build_faiss(self, vectors: np.ndarray):
        import faiss
        self._dimension = vectors.shape[1]
        self._index = faiss.IndexFlatIP(self._dimension)  # inner product for normalized vectors
        self._index.add(vectors.astype(np.float32))
        self._id_to_chunk = {i: c for i, c in enumerate(self._chunks)}

    def _save_index(self):
        import faiss
        path = os.path.join(self.index_path, "knowledge.index")
        faiss.write_index(self._index, path)
        chunks_path = os.path.join(self.index_path, "chunks.json")
        with open(chunks_path, "w", encoding="utf-8") as f:
            json.dump(self._chunks, f, ensure_ascii=False)
        # Save build metadata
        build_meta_path = os.path.join(self.index_path, "build_meta.json")
        with open(build_meta_path, "w", encoding="utf-8") as f:
            json.dump({
                "build_id": self._build_id,
                "document_count": len({c["metadata"]["file"] for c in self._chunks}),
                "chunk_count": len(self._chunks),
                "embedding_model": self._embedding_model,
                "dimension": self._dimension,
                "created_at": self._build_created_at,
                "duration_ms": self._build_duration_ms,
            }, f, ensure_ascii=False)
        logger.info("index saved: %s (%d vectors)", path, self._index.ntotal)

    def load_index(self) -> bool:
        """Load existing FAISS index and build metadata from disk."""
        import faiss
        idx_path = os.path.join(self.index_path, "knowledge.index")
        chunks_path = os.path.join(self.index_path, "chunks.json")
        if not os.path.exists(idx_path) or not os.path.exists(chunks_path):
            return False

        self._index = faiss.read_index(idx_path)
        self._dimension = self._index.d
        with open(chunks_path, "r", encoding="utf-8") as f:
            self._chunks = json.load(f)
        self._id_to_chunk = {i: c for i, c in enumerate(self._chunks)}
        # Load build metadata if present
        build_meta_path = os.path.join(self.index_path, "build_meta.json")
        if os.path.exists(build_meta_path):
            with open(build_meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
                self._build_id = meta.get("build_id", "")
                self._embedding_model = meta.get("embedding_model", "")
                self._build_created_at = meta.get("created_at", "")
                self._build_duration_ms = meta.get("duration_ms", 0)
        logger.info("index loaded: %d vectors", self._index.ntotal)
        return True

    @property
    def ready(self) -> bool:
        return self._index is not None and self._index.ntotal > 0

    # ---- search ----

    # Sections excluded from search results (meta-instructions / JSON blocks)
    _EXCLUDED_SECTIONS = {"可结构化字段", "RAG 使用建议", "适用场景", "文件列表"}

    @staticmethod
    def _matches_text_filter(value: str, tags: list, title: str) -> bool:
        """Check if *value* matches any tag or appears in the title.

        Uses bi-directional substring matching so that compound queries
        like ``occasion="户外婚礼"`` match individual tags like ``"户外"``
        or ``"婚礼"``, and vice versa.
        """
        if value in title:
            return True
        for tag in tags:
            if tag in value or value in tag:
                return True
        return False

    def search(
        self,
        query: str,
        gender: Optional[str] = None,
        category: Optional[str] = None,
        occasion: Optional[str] = None,
        season: Optional[str] = None,
        top_k: int = 5,
    ) -> dict:
        """Search the knowledge base with optional metadata filters.

        Returns::

            {
                "results": [
                    {
                        "content": "...",
                        "score": 0.82,
                        "file": "008-户外婚礼穿搭规则.md",
                        "title": "户外婚礼穿搭规则",
                        "section": "女生适配",
                        "chunkId": "008_xxx",
                        "metadata": {...}
                    }
                ],
                "query": "...",
                "rewritten_query": "...",
                "filters": {"gender": ..., "occasion": ..., "season": ..., "category": ...},
                "top_k": 5,
                "total_hits": N,
                "latency_ms": 50
            }
        """
        t0 = time.time()

        # Build rewritten query for observability
        filters = {}
        if gender and gender != "unknown":
            filters["gender"] = gender
        if occasion:
            filters["occasion"] = occasion
        if season:
            filters["season"] = season
        if category:
            filters["category"] = category

        if not self.ready:
            return {"results": [], "query": query, "rewritten_query": "", "filters": filters, "top_k": top_k, "total_hits": 0, "latency_ms": int((time.time() - t0) * 1000)}

        if not _ensure_embedder():
            raise RuntimeError("embedding model not available")

        q_vec = _embedder.encode([query], normalize_embeddings=True).astype(np.float32)

        # Fetch more than top_k to allow for metadata filtering
        fetch_k = min(top_k * 4, self._index.ntotal)
        scores, indices = self._index.search(q_vec, fetch_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self._chunks):
                continue
            chunk = self._chunks[idx]
            meta = chunk["metadata"]

            # Skip meta-instruction / JSON-block sections
            if meta.get("section", "") in self._EXCLUDED_SECTIONS:
                continue

            # Apply metadata filters (skip filter when value is "unknown" or "其他")
            if gender and gender != "unknown" and meta.get("gender") and meta["gender"] != gender:
                continue
            if category and meta.get("category") != category:
                continue
            if occasion and occasion != "其他":
                tags = meta.get("tags", [])
                title = meta.get("title", "")
                if not self._matches_text_filter(occasion, tags, title):
                    continue
            if season:
                tags = meta.get("tags", [])
                title = meta.get("title", "")
                if not self._matches_text_filter(season, tags, title):
                    continue

            results.append({
                "content": chunk["content"],
                "score": round(float(score), 4),
                "file": meta.get("file", ""),
                "title": meta.get("title", ""),
                "section": meta.get("section", ""),
                "chunkId": chunk["id"],
                "metadata": meta,
            })

            if len(results) >= top_k:
                break

        # Fallback: if filters reduced results below top_k, relax occasion filter
        if len(results) < top_k and occasion and occasion != "其他":
            relaxed = []
            for score, idx in zip(scores[0], indices[0]):
                if idx < 0 or idx >= len(self._chunks):
                    continue
                chunk = self._chunks[idx]
                meta = chunk["metadata"]
                if meta.get("section", "") in self._EXCLUDED_SECTIONS:
                    continue
                if gender and gender != "unknown" and meta.get("gender") and meta["gender"] != gender:
                    continue
                if category and meta.get("category") != category:
                    continue
                if season:
                    tags = meta.get("tags", [])
                    title = meta.get("title", "")
                    if not self._matches_text_filter(season, tags, title):
                        continue
                # Already in results? skip
                if any(r["chunkId"] == chunk["id"] for r in results):
                    continue
                relaxed.append({
                    "content": chunk["content"],
                    "score": round(float(score), 4),
                    "file": meta.get("file", ""),
                    "title": meta.get("title", ""),
                    "section": meta.get("section", ""),
                    "chunkId": chunk["id"],
                    "metadata": meta,
                })
                if len(results) + len(relaxed) >= top_k:
                    break
            results.extend(relaxed)

        return {
            "results": results,
            "query": query,
            "rewritten_query": "",
            "filters": filters,
            "top_k": top_k,
            "total_hits": len(results),
            "latency_ms": int((time.time() - t0) * 1000),
        }

    def get_stats(self) -> dict:
        if not self._chunks:
            return {"indexed": False, "chunks": 0, "files": 0}
        files = sorted({c["metadata"]["file"] for c in self._chunks})
        categories = sorted({c["metadata"]["category"] for c in self._chunks if c["metadata"].get("category")})
        stats = {
            "indexed": self.ready,
            "chunks": len(self._chunks),
            "files": len(files),
            "categories": categories,
            "dimension": self._dimension,
        }
        if self._build_id:
            stats["build"] = {
                "buildId": self._build_id,
                "documentCount": len(files),
                "chunkCount": len(self._chunks),
                "embeddingModel": self._embedding_model,
                "createdAt": self._build_created_at,
                "durationMs": self._build_duration_ms,
            }
        return stats
