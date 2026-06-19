"""MCP knowledge/RAG server — wraps the RAG knowledge service as MCP tools."""

import os

from mcp_servers.tool_registry import mcp_registry


def _get_knowledge_service():
    from knowledge.knowledge_service import KnowledgeService
    knowledge_dir = os.getenv("RAG_KNOWLEDGE_DIR", "")
    faiss_root = os.getenv("FAISS_INDEX_PATH", "")
    index_path = os.path.join(faiss_root, "knowledge") if faiss_root else ""
    svc = KnowledgeService(knowledge_dir, index_path)
    if not svc.ready:
        svc.load_index()
    return svc


def search_fashion_knowledge(query: str, gender: str = None, top_k: int = 5) -> dict:
    """检索时尚搭配知识库，返回相关的穿搭规则和建议。"""
    svc = _get_knowledge_service()
    if not svc.ready:
        return {"error": "knowledge index not available"}
    result = svc.search(query=query, gender=gender, top_k=top_k)
    return {
        "results": [
            {
                "title": r.get("title", ""),
                "section": r.get("section", ""),
                "content": r["content"][:300],
                "score": r["score"],
            }
            for r in result["results"]
        ],
        "total_hits": result["total_hits"],
    }


def get_fashion_recommendation(
    occasion: str = None,
    season: str = None,
    gender: str = None,
) -> dict:
    """根据场合和季节获取穿搭推荐，返回搭配规则和单品建议。"""
    svc = _get_knowledge_service()
    if not svc.ready:
        return {"error": "knowledge index not available"}

    queries = []
    if occasion:
        queries.append(occasion)
    if season:
        queries.append(season)
    query = " ".join(queries) if queries else "穿搭推荐"

    result = svc.search(query=query, gender=gender, top_k=5)
    recommendations = {"items": [], "rules": [], "avoid": []}
    for r in result["results"]:
        meta = r.get("metadata", {})
        recommendations["rules"].append(r["content"][:200])
        for item in meta.get("recommended_items", []):
            if item not in recommendations["items"]:
                recommendations["items"].append(item)
        for avoid in meta.get("avoid", []):
            if avoid not in recommendations["avoid"]:
                recommendations["avoid"].append(avoid)

    return recommendations


def register():
    """Register RAG knowledge tools with the MCP tool registry."""
    mcp_registry.register_server("aiwear-knowledge-rag", transport="in-process", description="RAG 时尚知识库 — 搜索 63 篇搭配规则")

    mcp_registry.register_tool(
        server="aiwear-knowledge-rag",
        name="search_fashion",
        description="搜索时尚搭配知识库，支持性别过滤，返回 match 的穿搭规则和章节",
        schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索查询，如 '户外婚礼雨天穿搭'"},
                "gender": {"type": "string", "enum": ["male", "female"]},
                "top_k": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
        callable_fn=search_fashion_knowledge,
    )

    mcp_registry.register_tool(
        server="aiwear-knowledge-rag",
        name="get_recommendation",
        description="根据场合和季节获取穿搭推荐，返回推荐单品、规则和避坑提醒",
        schema={
            "type": "object",
            "properties": {
                "occasion": {"type": "string", "description": "场合，如 '面试' '约会'"},
                "season": {"type": "string", "description": "季节，如 '春季' '冬季'"},
                "gender": {"type": "string", "enum": ["male", "female"]},
            },
        },
        callable_fn=get_fashion_recommendation,
    )
