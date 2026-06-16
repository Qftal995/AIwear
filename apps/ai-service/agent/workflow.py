from langgraph.graph import StateGraph, START, END
from agent.core import AgentState, init_models, create_aiwear_agent
from agent.middleware import ToolErrorHandler, ContextSummarizer, AgentStepTracker


def build_workflow(llm, tools: list, middleware: list = None) -> StateGraph:
    agent = create_aiwear_agent(tools=tools, middleware=middleware)
    step_tracker = AgentStepTracker() if middleware else None

    def audit_node(state: AgentState) -> AgentState:
        msg = state["messages"][-1].content
        result = llm.invoke([
            {"role": "system", "content": "检查用户输入是否安全，只返回 safe 或 unsafe。"},
            {"role": "user", "content": msg},
        ])
        content = result.content.strip().lower()
        state["audit_passed"] = content == "safe"
        if step_tracker:
            step_tracker.record(state, "audit")
        return state

    def retrieve_node(state: AgentState) -> AgentState:
        if not state.get("audit_passed", False):
            return state
        if step_tracker:
            step_tracker.record(state, "retrieve")
        return state

    def decide_node(state: AgentState) -> AgentState:
        last_msg = state["messages"][-1]
        has_tools = getattr(last_msg, "tool_calls", None)
        state["needs_tools"] = bool(has_tools)
        if step_tracker:
            step_tracker.record(state, "decide")
        return state

    def execute_node(state: AgentState) -> AgentState:
        if not state.get("needs_tools", False):
            return state
        result = agent.invoke(state)
        if step_tracker:
            step_tracker.record(state, "execute")
        return result

    builder = StateGraph(AgentState)
    builder.add_node("audit", audit_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("decide", decide_node)
    builder.add_node("execute", execute_node)
    builder.add_edge(START, "audit")
    builder.add_conditional_edges("audit", lambda s: "retrieve" if s.get("audit_passed", False) else END)
    builder.add_edge("retrieve", "decide")
    builder.add_conditional_edges("decide", lambda s: "execute" if s.get("needs_tools", False) else END)
    builder.add_edge("execute", END)
    return builder
