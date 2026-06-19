"""MCP geo-location server — in-process tool registration using 高德地图 API."""

import os
import urllib.request
import json as _json

from mcp_servers.tool_registry import mcp_registry

_geo_cache: dict[str, str] = {}

AMAP_KEY = os.getenv("AMAP_API_KEY", "")


def get_geolocation(ip: str = "") -> dict:
    """通过高德地图 IP 定位 API 获取城市地理位置信息。

    Args:
        ip: 客户端 IP 地址。传空字符串时高德自动使用请求来源 IP。

    Returns:
        dict with city, province, adcode fields.
    """
    if not AMAP_KEY:
        return {"city": "", "province": "", "adcode": "",
                "error": "高德地图 API Key 未配置，请设置环境变量 AMAP_API_KEY"}

    if ip in ("127.0.0.1", "localhost", "::1", ""):
        ip = ""

    cache_key = ip or "__auto__"
    if cache_key in _geo_cache:
        return {"city": _geo_cache[cache_key], "province": "", "adcode": "",
                "source": "cache"}

    try:
        params = f"key={AMAP_KEY}"
        if ip:
            params += f"&ip={ip}"
        url = f"https://restapi.amap.com/v3/ip?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "AIWear/2.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = _json.loads(resp.read().decode("utf-8"))

        if data.get("status") != "1":
            return {"city": "", "province": "", "adcode": "",
                    "error": f"高德 API 返回失败: {data.get('info', 'unknown')}"}

        city = data.get("city", "")
        province = data.get("province", "")
        adcode = data.get("adcode", "")

        if city:
            _geo_cache[cache_key] = city

        return {
            "city": city,
            "province": province,
            "adcode": adcode,
            "source": "amap",
        }
    except Exception as e:
        return {"city": "", "province": "", "adcode": "",
                "error": f"IP 定位失败: {e}"}


def reverse_geocode(lat: float, lng: float) -> dict:
    """通过高德逆地理编码将 GPS 经纬度转换为城市信息。

    Args:
        lat: 纬度 (latitude)，如 34.26316
        lng: 经度 (longitude)，如 108.94802

    Returns:
        dict with city, province, district, adcode, address fields.
    """
    if not AMAP_KEY:
        return {"city": "", "province": "", "district": "", "adcode": "",
                "error": "高德地图 API Key 未配置，请设置环境变量 AMAP_API_KEY"}

    cache_key = f"rg:{lat:.4f},{lng:.4f}"
    if cache_key in _geo_cache:
        return {"city": _geo_cache[cache_key], "province": "", "district": "",
                "adcode": "", "source": "cache"}

    try:
        url = (f"https://restapi.amap.com/v3/geocode/regeo?"
               f"key={AMAP_KEY}&location={lng},{lat}&extensions=base")
        req = urllib.request.Request(url, headers={"User-Agent": "AIWear/2.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = _json.loads(resp.read().decode("utf-8"))

        if data.get("status") != "1":
            return {"city": "", "province": "", "district": "", "adcode": "",
                    "error": f"高德逆地理编码失败: {data.get('info', 'unknown')}"}

        regeo = data.get("regeocode", {})
        addr = regeo.get("addressComponent", {})
        city = addr.get("city", "") or addr.get("province", "")
        province = addr.get("province", "")
        district = addr.get("district", "")
        adcode = addr.get("adcode", "")

        if city:
            _geo_cache[cache_key] = city

        return {
            "city": city,
            "province": province,
            "district": district,
            "adcode": adcode,
            "address": regeo.get("formatted_address", ""),
            "source": "amap_gps",
        }
    except Exception as e:
        return {"city": "", "province": "", "district": "", "adcode": "",
                "error": f"GPS 逆地理编码失败: {e}"}


def register():
    """Register geo-location tools with the MCP tool registry."""
    mcp_registry.register_server(
        "aiwear-geo", transport="in-process",
        description="高德地图 IP 定位 — 自动获取城市"
    )

    mcp_registry.register_tool(
        server="aiwear-geo",
        name="get_geolocation",
        description="通过 IP 地址获取用户所在城市。用于自动确定天气查询城市。"
                    "当用户未明确提供城市时调用此工具。"
                    "如果返回的城市为空或失败，应主动询问用户所在城市。",
        schema={
            "type": "object",
            "properties": {
                "ip": {"type": "string", "description": "客户端 IP 地址，留空自动获取"},
            },
            "required": [],
        },
        callable_fn=get_geolocation,
    )

    mcp_registry.register_tool(
        server="aiwear-geo",
        name="reverse_geocode",
        description="通过 GPS 经纬度获取城市信息。使用高德逆地理编码，精度可达街道级别。"
                    "当用户同意位置权限后，前端通过浏览器 Geolocation API 获取经纬度传入。",
        schema={
            "type": "object",
            "properties": {
                "lat": {"type": "number", "description": "纬度 (latitude)"},
                "lng": {"type": "number", "description": "经度 (longitude)"},
            },
            "required": ["lat", "lng"],
        },
        callable_fn=reverse_geocode,
    )
