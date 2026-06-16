import json

from langchain_core.tools import tool


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


@tool(description="查询时尚搭配知识，根据场合/季节/风格返回推荐。返回 JSON")
def get_fashion_knowledge_tool(occasion: str = None, season: str = None, style: str = None) -> str:
    results = {}
    if occasion:
        if occasion in _FASHION_KB:
            results["场合推荐"] = _FASHION_KB[occasion]
        else:
            for key in _FASHION_KB:
                if occasion in key:
                    results[key] = _FASHION_KB[key]
    if style:
        for key, info in _FASHION_KB.items():
            if any(style in s for s in info.get("风格", [])):
                if key not in results:
                    results[key] = info
    if results:
        return json.dumps(results, ensure_ascii=False)
    if occasion or style:
        return json.dumps({"提示": f"未找到匹配的场合知识，可用场合: {list(_FASHION_KB.keys())}"}, ensure_ascii=False)
    return json.dumps({"可用场合": list(_FASHION_KB.keys())}, ensure_ascii=False)


@tool(description="查询指定城市的天气，返回温度、天气状况、穿衣建议。返回 JSON")
def get_weather_tool(city: str = "北京") -> str:
    return json.dumps({
        "city": city,
        "temperature": 26,
        "condition": "晴",
        "humidity": "45%",
        "wind": "微风",
        "dressing_advice": "天气温暖，建议轻薄长袖或短袖+薄外套，紫外线中等注意防晒",
    }, ensure_ascii=False)
