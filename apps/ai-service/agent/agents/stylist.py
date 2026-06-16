from agent.core import init_models, create_aiwear_agent
from tools.wardrobe_tools import search_wardrobe_tool
from tools.rag_tools import get_fashion_knowledge_tool, get_weather_tool


def _create_user_preferences_tool(user_profile):
    from langchain_core.tools import tool
    import json

    @tool(description="读取用户穿搭偏好，返回用户喜欢的风格、场合、收藏。返回 JSON")
    def get_user_preferences_tool(user_id: str = "default") -> str:
        prefs = user_profile.get_preferences(user_id)
        history = user_profile.get_history(user_id, limit=5)
        return json.dumps({"preferences": prefs, "recent_history": history}, ensure_ascii=False)

    return get_user_preferences_tool


def create_stylist_agent(llm=None, user_profile=None) -> dict:
    if llm is None:
        llm = init_models()["planner"]
    system_prompt = "你是搭配推荐助手，根据检索到的衣物、用户偏好、时尚知识和天气，推荐最佳搭配组合。考虑场合、风格、颜色协调。"
    tools = [search_wardrobe_tool, get_fashion_knowledge_tool, get_weather_tool]
    if user_profile:
        tools.append(_create_user_preferences_tool(user_profile))
    agent = create_aiwear_agent(
        tools=tools,
        system_prompt=system_prompt,
    )
    return {"name": "stylist", "agent": agent, "description": "搭配推荐助手"}


def run_stylist(state: dict, user_profile) -> dict:
    wardrobe_context = state.get("wardrobe_context", [])
    preferences = user_profile.get_preferences(state.get("user_id", "default"))
    context = f"衣物: {wardrobe_context}\n偏好: {preferences}"
    state["styling_context"] = context
    return state
