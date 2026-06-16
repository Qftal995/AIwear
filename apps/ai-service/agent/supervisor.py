from langgraph.graph import StateGraph, START, END
from agent.core import AgentState, init_models, create_aiwear_agent


def create_supervisor(llm, sub_agents: list) -> object:
    intent_prompt = (
        "分析用户意图，从以下分类中选择一个或多个：wardrobe, stylist, visualizer, auditor, copywriter。"
        "wardrobe：衣物检索；stylist：搭配推荐；visualizer：图片处理；auditor：内容审核；copywriter：文案撰写。"
        "只返回分类名称，用逗号分隔。"
    )

    agent_map = {}
    for sa in sub_agents:
        name = sa["name"] if isinstance(sa, dict) else sa
        agent_map[name] = sa

    def supervisor_node(state: AgentState) -> AgentState:
        msg = state["messages"][-1].content
        result = llm.invoke([
            {"role": "system", "content": intent_prompt},
            {"role": "user", "content": msg},
        ])
        selected = [s.strip() for s in result.content.split(",") if s.strip()]
        state["intents"] = selected if selected else ["wardrobe"]
        return state

    def route_node(state: AgentState) -> AgentState:
        intents = state.get("intents", ["wardrobe"])
        results = []
        for intent in intents:
            if intent in agent_map:
                sub = agent_map[intent]
                sub_agent = sub["agent"] if isinstance(sub, dict) else sub
                try:
                    sub_result = sub_agent.invoke(state)
                    results.append({
                        "agent": intent,
                        "output": sub_result["messages"][-1].content,
                    })
                except Exception as exc:
                    results.append({
                        "agent": intent,
                        "output": f"error: {exc}",
                    })
        state["sub_agent_results"] = results
        return state

    def aggregate_node(state: AgentState) -> AgentState:
        results = state.get("sub_agent_results", [])
        if not results:
            return state
        parts = "\n".join(f"[{r['agent']}]: {r['output']}" for r in results)
        result = llm.invoke([
            {"role": "system", "content": "你是AIWear虚拟试衣助手，整合多个助手结果生成连贯回复。"},
            {"role": "user", "content": parts},
        ])
        from langchain_core.messages import AIMessage
        state["messages"] = list(state["messages"]) + [AIMessage(content=result.content)]
        return state

    builder = StateGraph(AgentState)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("route", route_node)
    builder.add_node("aggregate", aggregate_node)
    builder.add_edge(START, "supervisor")
    builder.add_edge("supervisor", "route")
    builder.add_edge("route", "aggregate")
    builder.add_edge("aggregate", END)
    compiled = builder.compile()
    return compiled
