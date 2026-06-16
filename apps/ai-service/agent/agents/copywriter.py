from agent.core import init_models, create_aiwear_agent


def create_copywriter_agent(llm=None) -> dict:
    if llm is None:
        llm = init_models()["planner"]
    system_prompt = "你是时尚文案助手，为搭配结果撰写简洁优雅的描述文案。包括穿搭要点、适合场合、风格说明。"
    agent = create_aiwear_agent(
        tools=[],
        system_prompt=system_prompt,
    )
    return {"name": "copywriter", "agent": agent, "description": "时尚文案助手"}


def run_copywriter(state: dict) -> dict:
    wardrobe_ctx = state.get("wardrobe_context", "")
    styling_ctx = state.get("styling_context", "")
    combined = f"衣物: {wardrobe_ctx}\n搭配: {styling_ctx}"
    state["copywriting_input"] = combined
    return state
