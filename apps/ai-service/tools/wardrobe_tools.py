import json

from langchain_core.tools import tool


@tool(description="搜索用户衣橱，支持文本描述和属性过滤，返回匹配单品列表 JSON")
def search_wardrobe_tool(query: str, user_id: str, category: str = None, color: str = None, style: str = None) -> str:
    from memory.wardrobe_store import WardrobeStore
    from vector_store.faiss_store import FAISSStore
    import os

    index_path = os.getenv("FAISS_INDEX_PATH")
    store = WardrobeStore(index_path=index_path)
    filters = {}
    if category:
        filters["category"] = category
    if color:
        filters["color"] = color
    if style:
        filters["style"] = style
    results = store.search(user_id=user_id, query=query, filters=filters or None)
    data = [
        {
            "image_id": r["image_id"],
            "similarity": round(r["similarity"], 4),
            "description": r["metadata"].get("description", ""),
            "tags": r["metadata"].get("tags", {}),
        }
        for r in results
    ]
    return json.dumps({"success": True, "items": data, "total": len(data)}, ensure_ascii=False)


@tool(description="添加单品到用户衣橱，接收图片数据和元信息，返回添加结果 JSON")
def add_to_wardrobe_tool(user_id: str, image_url: str, description: str = "", category: str = "", color: str = "", style: str = "", season: str = "") -> str:
    from memory.wardrobe_store import WardrobeStore
    import requests
    import os

    index_path = os.getenv("FAISS_INDEX_PATH")
    store = WardrobeStore(index_path=index_path)
    try:
        if image_url.startswith("http"):
            resp = requests.get(image_url, timeout=20)
            resp.raise_for_status()
            image_data = resp.content
        else:
            return json.dumps({"success": False, "error": "image_url must be a valid HTTP URL"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"download failed: {e}"}, ensure_ascii=False)

    tags = {"category": category, "color": color, "style": style, "season": season}
    result = store.add_item(user_id=user_id, image_data=image_data, image_url=image_url, description=description, tags=tags)
    store.store.save()
    return json.dumps({"success": True, "image_id": result["image_id"]}, ensure_ascii=False)


@tool(description="删除衣橱中的指定单品，返回删除结果 JSON")
def remove_from_wardrobe_tool(user_id: str, image_id: str) -> str:
    import os
    from memory.wardrobe_store import WardrobeStore

    index_path = os.getenv("FAISS_INDEX_PATH")
    store = WardrobeStore(index_path=index_path)
    store.delete_item(image_id)
    store.store.save()
    return json.dumps({"success": True, "deleted": image_id}, ensure_ascii=False)
