import uuid

from utils.clip_utils import clip_image_to_512d
from vector_store.faiss_store import FAISSStore


class WardrobeStore:
    def __init__(self, index_path: str = None):
        self.store = FAISSStore(dimension=512, index_path=index_path)

    def add_item(self, user_id: str, image_data: bytes, image_url: str, description: str = "", tags: dict = None) -> dict:
        image_id = str(uuid.uuid4())
        embedding = clip_image_to_512d(image_data)
        if tags is None:
            tags = {"category": "", "color": "", "style": "", "season": ""}
        metadata = {
            "user_id": user_id,
            "oss_url": image_url,
            "description": description,
            "tags": tags,
        }
        self.store.add(image_id=image_id, embedding=embedding, metadata=metadata)
        return {"image_id": image_id, "metadata": metadata}

    def search(self, user_id: str, query: str, filters: dict = None, top_k: int = 10) -> list[dict]:
        return self.store.search_by_text(query=query, user_id=user_id, top_k=top_k)

    def search_by_image(self, user_id: str, image_data: bytes, top_k: int = 5) -> list[dict]:
        query_vector = clip_image_to_512d(image_data)
        return self.store.search_by_vector(
            query_vec=query_vector, user_id=user_id, top_k=top_k
        )

    def get_user_items(self, user_id: str) -> list[dict]:
        return self.store.get_by_user(user_id)

    def delete_item(self, image_id: str) -> None:
        self.store.delete(image_id)
