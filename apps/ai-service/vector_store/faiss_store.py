import faiss
import numpy as np
import pickle
import threading
import difflib
import re
import os


def _normalize_text(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r'[^\w\s一-鿿]', '', s)
    s = re.sub(r'\s+', ' ', s)
    return s


def _text_similarity(q: str, d: str) -> float:
    qn = _normalize_text(q)
    dn = _normalize_text(d)
    if not qn or not dn:
        return 0.0
    ratio = difflib.SequenceMatcher(None, qn, dn).ratio()
    qg = set(qn[i:i+2] for i in range(len(qn)-1))
    dg = set(dn[i:i+2] for i in range(len(dn)-1))
    if not qg or not dg:
        return ratio
    jaccard = len(qg & dg) / len(qg | dg)
    return max(ratio, jaccard)


class FAISSStore:
    def __init__(self, dimension: int = 512, index_path: str = None):
        """index_path: directory to persist FAISS index files."""
        self._index = faiss.IndexFlatIP(dimension)
        self._image_ids = []
        self._metadata = []
        self._user_index = {}
        self._deleted = set()
        self._lock = threading.Lock()
        self._index_path = index_path
        if index_path and os.path.isdir(index_path):
            self.load()

    def add(self, image_id: str, embedding: list[float], metadata: dict) -> None:
        with self._lock:
            self._index.add(np.array([embedding], dtype=np.float32))
            pos = self._index.ntotal - 1
            self._image_ids.append(image_id)
            self._metadata.append(metadata)
            uid = metadata.get('user_id')
            if uid:
                self._user_index.setdefault(uid, set()).add(pos)

    def add_batch(self, items: list[dict]) -> None:
        with self._lock:
            vecs = np.array([i['embedding'] for i in items], dtype=np.float32)
            self._index.add(vecs)
            start = self._index.ntotal - len(items)
            for i, item in enumerate(items):
                pos = start + i
                self._image_ids.append(item['image_id'])
                self._metadata.append(item['metadata'])
                uid = item['metadata'].get('user_id')
                if uid:
                    self._user_index.setdefault(uid, set()).add(pos)

    def search_by_vector(self, query_vec: list[float], user_id: str = None, top_k: int = 10, min_similarity: float = 0.7) -> list[dict]:
        with self._lock:
            n = self._index.ntotal
            if n == 0:
                return []
            distances, indices = self._index.search(np.array([query_vec], dtype=np.float32), min(top_k * 3, n))
            allowed = self._user_index.get(user_id) if user_id else None
            results = []
            for dist, idx in zip(distances[0], indices[0]):
                if idx == -1 or idx in self._deleted:
                    continue
                if allowed is not None and idx not in allowed:
                    continue
                if dist >= min_similarity:
                    results.append({
                        'image_id': self._image_ids[idx],
                        'similarity': float(dist),
                        'metadata': self._metadata[idx],
                    })
            results.sort(key=lambda x: x['similarity'], reverse=True)
            return results[:top_k]

    def search_by_text(self, query: str, user_id: str = None, top_k: int = 10, min_similarity: float = 0.1) -> list[dict]:
        with self._lock:
            results = []
            for idx, mid in enumerate(self._image_ids):
                if mid is None or idx in self._deleted:
                    continue
                meta = self._metadata[idx]
                if user_id and meta.get('user_id') != user_id:
                    continue
                sim = _text_similarity(query, meta.get('description', ''))
                if sim >= min_similarity:
                    results.append({
                        'image_id': mid,
                        'similarity': sim,
                        'metadata': meta,
                    })
            results.sort(key=lambda x: x['similarity'], reverse=True)
            return results[:top_k]

    def delete(self, image_id: str) -> None:
        with self._lock:
            for idx, mid in enumerate(self._image_ids):
                if mid == image_id:
                    self._image_ids[idx] = None
                    self._metadata[idx] = None
                    self._deleted.add(idx)
                    for positions in self._user_index.values():
                        positions.discard(idx)
                    return

    def count(self) -> int:
        with self._lock:
            return sum(1 for x in self._image_ids if x is not None)

    def save(self) -> None:
        if not self._index_path:
            return
        os.makedirs(self._index_path, exist_ok=True)
        with self._lock:
            faiss.write_index(self._index, os.path.join(self._index_path, 'index.faiss'))
            data = {
                'image_ids': self._image_ids,
                'metadata': self._metadata,
                'user_index': self._user_index,
                'deleted': self._deleted,
            }
            with open(os.path.join(self._index_path, 'data.pkl'), 'wb') as f:
                pickle.dump(data, f)

    def load(self) -> None:
        if not self._index_path:
            return
        idx_file = os.path.join(self._index_path, 'index.faiss')
        dat_file = os.path.join(self._index_path, 'data.pkl')
        if not os.path.isfile(idx_file) or not os.path.isfile(dat_file):
            return
        with self._lock:
            self._index = faiss.read_index(idx_file)
            with open(dat_file, 'rb') as f:
                data = pickle.load(f)
            self._image_ids = data['image_ids']
            self._metadata = data['metadata']
            self._user_index = data['user_index']
            self._deleted = data['deleted']

    def get_by_user(self, user_id: str) -> list[dict]:
        with self._lock:
            results = []
            for pos in self._user_index.get(user_id, set()):
                if pos in self._deleted or self._image_ids[pos] is None:
                    continue
                results.append({
                    'image_id': self._image_ids[pos],
                    'metadata': self._metadata[pos],
                })
            return results
