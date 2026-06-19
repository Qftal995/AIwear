import json
import os
import socket
import urllib.request
import urllib.parse
import urllib.error
import ssl


class WeatherService:
    """Weather API service using 心知天气 (Seniverse).

    Extracted from rag_tools.py for reuse by MCP servers and Agent tools.
    """

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("XINZHI_WEATHER_KEY", "")

    def get_weather(self, city: str = "北京") -> dict:
        """Get current weather and dressing advice for a city.

        Returns always include ``success`` (bool) and ``source`` (str):
        - ``api``: real Seniverse API success
        - ``mock``: no API key configured
        - ``fallback``: API call failed after timeout
        """
        if not self.api_key:
            result = self._mock_weather(city)
            result["success"] = True
            result["source"] = "mock"
            return result

        try:
            params = urllib.parse.urlencode({
                "key": self.api_key, "location": city,
                "language": "zh-Hans", "unit": "c",
            })
            url = f"https://api.seniverse.com/v3/weather/now.json?{params}"
            req = urllib.request.Request(url, headers={"User-Agent": "AIWear/2.0"})
            ctx = ssl.create_default_context()

            # Bypass the IPv4-only monkey-patch for this API call
            _orig = getattr(socket, "_orig_getaddrinfo", None)
            if _orig:
                socket.getaddrinfo = _orig
            with urllib.request.urlopen(req, timeout=3, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            result = data["results"][0]
            now = result["now"]
            loc = result["location"]
            temp = int(now["temperature"])
            humidity = now.get("humidity", "")
            wind_dir = now.get("wind_direction", "")
            wind_speed = now.get("wind_speed", "")
            wind = f"{wind_dir} {wind_speed} km/h".strip() if (wind_dir or wind_speed) else "微风"
            return {
                "success": True,
                "source": "api",
                "city": loc["name"],
                "temperature": temp,
                "condition": now["text"],
                "humidity": f"{humidity}%" if humidity else "",
                "wind": wind,
                "dressing_advice": self._dressing_advice(temp),
            }
        except Exception as e:
            return {
                "success": False,
                "source": "fallback",
                "city": city,
                "error": str(e),
                "dressing_advice": "天气数据暂不可用，请根据季节自行搭配",
            }

    @staticmethod
    def _dressing_advice(temp: int) -> str:
        if temp < 10:
            return "天气寒冷，建议穿厚外套、毛衣、围巾，注意保暖"
        elif temp < 20:
            return "天气微凉，建议穿薄外套、长袖或针织衫"
        elif temp < 28:
            return "天气温暖，建议轻薄长袖或短袖+薄外套"
        elif temp < 35:
            return "天气较热，建议短袖、裙子、短裤，注意防晒"
        else:
            return "天气炎热，建议轻薄透气衣物，避免暴晒"

    @staticmethod
    def _mock_weather(city: str) -> dict:
        return {
            "city": city,
            "temperature": 26,
            "condition": "晴",
            "dressing_advice": "天气温暖，建议轻薄长袖或短袖+薄外套（mock数据，未配置天气API key）",
        }
