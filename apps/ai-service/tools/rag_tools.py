import json
import os
import time

import requests
from langchain_core.tools import tool


# In-memory web search cache (1 hour TTL)
_WEB_CACHE: dict[str, dict] = {}
_WEB_CACHE_TTL = 3600  # seconds


# ── Hardcoded KB (fallback when RAG index not available) ──────────
_FASHION_KB = {
    "约会": {
        "风格": ["温柔", "甜美", "优雅"],
        "单品": ["连衣裙", "半身裙", "针织衫", "高跟鞋"],
        "配色": ["粉色系", "米色系", "浅蓝"],
    },
    "通勤": {
        "风格": ["简约", "利落", "职业"],
        "单品": ["西装外套", "直筒裤", "衬衫", "乐福鞋"],
        "配色": ["黑白灰", "藏青", "驼色"],
    },
    "运动": {
        "风格": ["休闲", "活力", "街头"],
        "单品": ["卫衣", "运动裤", "T恤", "运动鞋"],
        "配色": ["黑白", "亮色点缀"],
    },
    "晚宴": {
        "风格": ["华丽", "性感", "气场"],
        "单品": ["礼服裙", "高跟鞋", "手拿包", "珠宝配饰"],
        "配色": ["黑金", "红色", "深蓝"],
    },
    "日常": {
        "风格": ["舒适", "百搭", "休闲"],
        "单品": ["牛仔裤", "白T", "针织开衫", "小白鞋"],
        "配色": ["牛仔蓝", "白色", "卡其"],
    },
    "出游": {
        "风格": ["清新", "度假", "文艺"],
        "单品": ["碎花裙", "草帽", "帆布鞋", "墨镜"],
        "配色": ["碎花", "浅色系", "草编"],
    },
}


def _get_knowledge_service():
    """Lazy init the RAG knowledge service. Returns None if not available."""
    try:
        from knowledge.knowledge_service import KnowledgeService
        import os
        knowledge_dir = os.getenv("RAG_KNOWLEDGE_DIR", "")
        faiss_root = os.getenv("FAISS_INDEX_PATH", "")
        if not knowledge_dir:
            return None
        index_path = os.path.join(faiss_root, "knowledge") if faiss_root else ""
        svc = KnowledgeService(knowledge_dir, index_path)
        if svc.load_index() or True:
            return svc
    except Exception:
        pass
    return None


@tool(description="查询时尚搭配知识，根据场合/季节/风格返回推荐。返回 JSON")
def get_fashion_knowledge_tool(occasion: str = "", season: str = "", style: str = "") -> str:
    # Try real RAG knowledge base first
    svc = _get_knowledge_service()
    if svc and svc.ready:
        query = f"{occasion or ''} {season or ''} {style or ''}".strip()
        if not query:
            return json.dumps({"results": [], "note": "no query terms provided"}, ensure_ascii=False)
        result = svc.search(query=query, top_k=3)
        if result["results"]:
            items = []
            for r in result["results"]:
                items.append({
                    "title": r.get("title", ""),
                    "section": r.get("section", ""),
                    "content": r.get("content", "")[:300],
                    "score": r.get("score", 0),
                })
            return json.dumps({"source": "rag_knowledge_base", "results": items}, ensure_ascii=False)

    # Fallback to hardcoded KB
    results = {}
    if occasion:
        for key in _FASHION_KB:
            if occasion in key or key in occasion:
                results[key] = _FASHION_KB[key]
    if style:
        for key, info in _FASHION_KB.items():
            if any(style in s for s in info.get("风格", [])):
                if key not in results:
                    results[key] = info
    if results:
        return json.dumps({"source": "hardcoded_kb", "results": results}, ensure_ascii=False)
    if occasion or style:
        return json.dumps({"提示": f"未找到匹配的搭配知识"}, ensure_ascii=False)
    return json.dumps({"提示": "请提供场合、季节或风格信息"}, ensure_ascii=False)


@tool(description="查询指定城市的天气，返回温度、天气状况、穿衣建议。返回 JSON")
def get_weather_tool(city: str = "北京") -> str:
    from services.weather_service import WeatherService
    svc = WeatherService()
    result = svc.get_weather(city)
    return json.dumps(result, ensure_ascii=False)


@tool(description="获取内外部时尚搭配知识。优先使用本地知识库，网络搜索作为补充。返回 JSON")
def get_external_fashion_knowledge_tool(occasion: str = "", season: str = "", style: str = "") -> str:
    """Combined RAG KB + hardcoded fallback + web search fashion knowledge."""
    result = {
        "local_kb": None,
        "web_search": None,
        "sources": [],
    }

    # Step 1: Try real RAG knowledge base
    svc = _get_knowledge_service()
    if svc and svc.ready:
        query = f"{occasion or ''} {season or ''} {style or ''}".strip()
        if query:
            rag_result = svc.search(query=query, top_k=3)
            if rag_result["results"]:
                result["local_kb"] = {
                    "source": "rag_index",
                    "results": [
                        {"title": r.get("title", ""), "section": r.get("section", ""),
                         "content": r.get("content", "")[:300], "score": r.get("score", 0)}
                        for r in rag_result["results"]
                    ],
                }
                result["sources"].append("rag_index")

    # Step 2: Fallback to hardcoded KB
    if not result["local_kb"]:
        local_result = {}
        if occasion:
            for key in _FASHION_KB:
                if occasion in key or key in occasion:
                    local_result[key] = _FASHION_KB[key]
        if style:
            for key, info in _FASHION_KB.items():
                if any(style in s for s in info.get("风格", [])):
                    if key not in local_result:
                        local_result[key] = info
        if local_result:
            result["local_kb"] = {"source": "hardcoded_kb", "results": local_result}
            result["sources"].append("hardcoded_kb")
        else:
            result["local_kb"] = {"note": "no local match found"}

    # Step 3: Web search supplement
    needs_web = not result["sources"] or "hardcoded_kb" in result["sources"]
    if needs_web:
        web_query = f"{occasion or ''} {style or ''} 穿搭搭配推荐".strip()
        if not web_query:
            web_query = "时尚穿搭推荐"

        cache_key = web_query
        if cache_key in _WEB_CACHE:
            cached = _WEB_CACHE[cache_key]
            if time.time() - cached["ts"] < _WEB_CACHE_TTL:
                result["web_search"] = cached["data"]
                result["sources"].append("web_search_cache")
            else:
                del _WEB_CACHE[cache_key]

        if result.get("web_search") is None:
            try:
                from tools.web_search_tool import web_search_tool
                web_result_str = web_search_tool.invoke({"query": web_query})
                web_data = json.loads(web_result_str)
                result["web_search"] = web_data
                result["sources"].append("web_search")
                _WEB_CACHE[cache_key] = {"ts": time.time(), "data": web_data}
            except Exception:
                result["web_search"] = {"results": [], "note": "Web search unavailable"}
                result["sources"].append("web_search_error")

    return json.dumps(result, ensure_ascii=False)
