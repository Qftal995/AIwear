"""MCP weather server — in-process tool registration."""

from mcp_servers.tool_registry import mcp_registry


def _get_weather_service():
    from services.weather_service import WeatherService
    return WeatherService()


def query_weather(city: str = "北京") -> dict:
    """查询指定城市的天气，返回温度、天气状况和穿搭建议。"""
    svc = _get_weather_service()
    return svc.get_weather(city)


def query_weather_dressing_advice(city: str = "北京") -> dict:
    """查询指定城市的天气并返回针对性的穿搭约束建议。"""
    svc = _get_weather_service()
    result = svc.get_weather(city)
    return {
        "success": result.get("success", True),
        "source": result.get("source", "unknown"),
        "city": result.get("city", city),
        "temperature": result.get("temperature"),
        "condition": result.get("condition"),
        "advice": result.get("dressing_advice"),
        "constraints": _advice_to_constraints(result.get("dressing_advice", "")),
    }


def _advice_to_constraints(advice: str) -> dict:
    """Convert dressing advice text to structured constraints."""
    constraints = {"layers": "medium", "accessories": [], "avoid": []}
    if "厚外套" in advice or "毛衣" in advice:
        constraints["layers"] = "heavy"
    elif "短袖" in advice or "热" in advice:
        constraints["layers"] = "light"
    if "防晒" in advice:
        constraints["accessories"].append("防晒")
    if "围巾" in advice:
        constraints["accessories"].append("围巾")
    return constraints


def register():
    """Register weather tools with the MCP tool registry."""
    mcp_registry.register_server("aiwear-weather", transport="in-process", description="心知天气 API — 查询城市天气和穿搭建议")

    mcp_registry.register_tool(
        server="aiwear-weather",
        name="get_weather",
        description="查询指定城市的当前天气，返回温度、天气状况、湿度、风向和穿搭建议",
        schema={
            "type": "object",
            "properties": {"city": {"type": "string", "description": "城市名称，如 '杭州'"}},
            "required": ["city"],
        },
        callable_fn=query_weather,
    )

    mcp_registry.register_tool(
        server="aiwear-weather",
        name="get_dressing_advice",
        description="查询城市天气并返回结构化穿搭约束（层次、配饰、避坑）",
        schema={
            "type": "object",
            "properties": {"city": {"type": "string", "description": "城市名称"}},
            "required": ["city"],
        },
        callable_fn=query_weather_dressing_advice,
    )
