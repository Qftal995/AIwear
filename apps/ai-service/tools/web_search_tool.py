"""
Web search tool for fashion/styling knowledge augmentation.

Uses DuckDuckGo (no API key required) via the ``duckduckgo_search`` library.
Falls back gracefully if the library is not installed.
"""

import json
from typing import Optional

from langchain_core.tools import tool

try:
    from duckduckgo_search import DDGS

    _HAS_DDG = True
except ImportError:
    _HAS_DDG = False


@tool(description="搜索网络上的时尚/穿搭/造型知识。当本地知识不足时使用，返回前5条结果含标题、摘要、链接。返回 JSON")
def web_search_tool(query: str, max_results: int = 5) -> str:
    """Search the web for fashion/styling knowledge.

    Args:
        query: 搜索关键词（如"约会穿搭推荐 2025"）
        max_results: 返回结果数量，默认 5

    Returns:
        JSON string with list of ``{title, snippet, url}`` results.
    """
    if not _HAS_DDG:
        return json.dumps(
            {
                "results": [],
                "note": "Web search unavailable - duckduckgo_search not installed. "
                "Run: pip install duckduckgo_search",
                "source": "web_search",
            },
            ensure_ascii=False,
        )

    try:
        with DDGS() as ddgs:
            raw_results = list(ddgs.text(query, max_results=max_results))

        results = []
        for r in raw_results:
            results.append(
                {
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                    "url": r.get("href", ""),
                }
            )

        return json.dumps(
            {
                "query": query,
                "results": results,
                "result_count": len(results),
                "source": "web_search",
            },
            ensure_ascii=False,
        )
    except Exception as e:
        return json.dumps(
            {
                "query": query,
                "results": [],
                "error": str(e),
                "source": "web_search",
            },
            ensure_ascii=False,
        )
