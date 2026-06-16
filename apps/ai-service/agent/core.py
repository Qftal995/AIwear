import os
from typing import TypedDict, Annotated, Sequence

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_community.chat_models.tongyi import ChatTongyi


class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    user_id: str
    wardrobe_context: dict
    session_id: str
    intermediate_steps: list


def init_models():
    return {
        "planner": ChatOpenAI(
            model="deepseek-chat",
            temperature=0.1,
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com/v1",
        ),
        "vision": ChatTongyi(
            model="qwen-vl-max", temperature=0.0, dashscope_api_key=os.getenv("DASHSCOPE_API_KEY")
        ),
    }


def create_aiwear_agent(
    tools: list, middleware: list = None, system_prompt: str = ""
) -> CompiledStateGraph:
    if not system_prompt:
        system_prompt = (
            "你是衣览无余AI穿搭助手，可以调用工具处理图片、检索衣橱、推荐搭配。"
            "最终输出JSON格式。"
        )
    models = init_models()
    return create_agent(
        model=models["planner"],
        tools=tools,
        system_prompt=system_prompt,
        middleware=middleware or [],
        state_schema=AgentState,
    )
