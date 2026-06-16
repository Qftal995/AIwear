from agent.core import init_models, create_aiwear_agent


def create_auditor_agent(llm=None) -> dict:
    if llm is None:
        llm = init_models()["planner"]
    system_prompt = "你是内容安全审核助手，检查生成的图片和文案是否符合安全规范。只输出通过或不通过。"
    agent = create_aiwear_agent(
        tools=[],
        system_prompt=system_prompt,
    )
    return {"name": "auditor", "agent": agent, "description": "内容安全审核助手"}


def run_auditor(state: dict) -> dict:
    last_msg = state["messages"][-1].content if state["messages"] else ""
    state["audit_target"] = last_msg
    state["audit_result"] = "pending"
    return state
