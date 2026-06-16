from agent.core import init_models, create_aiwear_agent


def create_stylist_agent(llm=None) -> dict:
    if llm is None:
        llm = init_models()["planner"]
    system_prompt = "你是搭配推荐助手，根据检索到的衣物和用户偏好，推荐最佳搭配组合。考虑场合、风格、颜色协调。"
    agent = create_aiwear_agent(
        tools=[],
        system_prompt=system_prompt,
    )
    return {"name": "stylist", "agent": agent, "description": "搭配推荐助手"}


def run_stylist(state: dict, user_profile) -> dict:
    wardrobe_context = state.get("wardrobe_context", [])
    preferences = user_profile.get_preferences(state.get("user_id", "default"))
    context = f"衣物: {wardrobe_context}\n偏好: {preferences}"
    state["styling_context"] = context
    return state
