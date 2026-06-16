from agent.core import init_models, create_aiwear_agent


def create_wardrobe_agent(llm=None, vector_store=None) -> dict:
    if llm is None:
        llm = init_models()["planner"]
    system_prompt = "你是衣橱检索助手，根据用户需求从衣橱中找到合适的衣物。返回找到的衣物列表和匹配理由。"
    agent = create_aiwear_agent(
        tools=[],
        system_prompt=system_prompt,
    )
    return {"name": "wardrobe", "agent": agent, "description": "衣橱检索助手"}


def run_wardrobe(state: dict, wardrobe_store) -> dict:
    query = state["messages"][-1].content
    items = wardrobe_store.search(user_id=state.get("user_id", "default"), query=query)
    context = []
    for item in items[:5]:
        desc = item["metadata"].get("description", "")
        tags = item["metadata"].get("tags", {})
        context.append(f"- {desc} [{tags}]")
    state["wardrobe_context"] = context
    return state
