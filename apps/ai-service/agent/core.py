import os
from typing import TypedDict, Annotated, Sequence, Optional

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from langchain_community.chat_models.tongyi import ChatTongyi


class AgentState(TypedDict, total=False):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    remaining_steps: int  # v2 state schema required field
    user_id: str
    wardrobe_context: dict
    session_id: str
    intermediate_steps: list
    # intent classification
    intents: list
    intent: str
    gender: str
    occasion: str
    city: str
    style: str
    # planning
    tool_plan: dict
    # execution
    tool_results: list
    sub_agent_results: list
    citations: list
    # hitl
    needs_hitl: bool
    hitl: dict
    paused: bool
    user_choice: str
    # context
    original_query: str
    mcp_tools: list
    user_preferences: dict
    client_ip: str
    latitude: float
    longitude: float
    city_source: str
    image_urls: list


class AgentResult(TypedDict, total=False):
    """Unified structured output for all sub-agents."""
    agent: str
    status: str          # success | failed | partial
    confidence: float    # 0.0–1.0
    summary: str         # one-line summary for the Supervisor
    result: dict         # agent-specific payload
    citations: list      # RAG citations used
    needs_handoff: bool  # signal handoff to visualizer
    next_agent: str      # target agent if handoff
    warnings: list       # non-fatal issues
    error: str           # failure reason when status=failed


def parse_agent_result(output: str, agent_name: str) -> AgentResult:
    """Parse an agent's output into a structured AgentResult.

    If the output is valid JSON containing at least ``status``, it is
    treated as an AgentResult.  Otherwise the raw text is wrapped as a
    plain ``success`` result with the text in ``summary``.
    """
    import json
    try:
        # Try to extract JSON block from markdown code fences
        content = output.strip()
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        data = json.loads(content)
        if isinstance(data, dict) and "status" in data:
            data.setdefault("agent", agent_name)
            data.setdefault("summary", str(data.get("result", ""))[:200])
            data.setdefault("confidence", 0.8)
            return data
    except (json.JSONDecodeError, Exception):
        pass
    # Fallback: wrap raw text
    return {
        "agent": agent_name,
        "status": "success",
        "confidence": 0.7,
        "summary": output[:200],
        "result": {"raw_output": output},
    }


def init_models():
    return {
        "planner": ChatOpenAI(
            model="deepseek-chat",
            temperature=0.1,
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com/v1",
            timeout=25,
            max_retries=1,
        ),
        "vision": ChatTongyi(
            model="qwen-vl-max", temperature=0.0, dashscope_api_key=os.getenv("DASHSCOPE_API_KEY")
        ),
    }


def create_aiwear_agent(
    tools: list,
    middleware: list = None,
    system_prompt: str = "",
    mcp_tools: Optional[list] = None,
) -> CompiledStateGraph:
    """Create a LangGraph ReAct agent with optional MCP-discovered tools.

    Args:
        tools: List of langchain tools available to the agent.
        middleware: Optional list of LangGraph middleware.
        system_prompt: System prompt for the agent.
        mcp_tools: Optional list of langchain tools discovered from MCP
            servers (see :class:`utils.mcp_client.MCPClientManager`).
            These are merged with ``tools`` so the agent can call them
            alongside built-in tools.

    Returns:
        A compiled ``StateGraph`` ready for invocation.
    """
    if not system_prompt:
        system_prompt = (
            "你是衣览无余AI穿搭助手，可以调用工具处理图片、检索衣橱、推荐搭配。"
            "最终输出JSON格式。"
        )
    models = init_models()

    # Merge built-in tools with MCP-discovered tools
    all_tools = list(tools)
    if mcp_tools:
        all_tools.extend(mcp_tools)

    return create_react_agent(
        model=models["planner"],
        tools=all_tools,
        prompt=system_prompt,
        state_schema=AgentState,
    )
