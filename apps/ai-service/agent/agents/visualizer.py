from agent.core import init_models, create_aiwear_agent
from tools.image_tools import edit_image_tool, merge_image_tool, image_description_tool


def create_visualizer_agent(llm=None, tools=None) -> dict:
    if llm is None:
        llm = init_models()["planner"]
    if tools is None:
        tools = [edit_image_tool, merge_image_tool, image_description_tool]
    system_prompt = "你是图片处理助手，调用图片编辑和合并工具生成试穿效果图。"
    agent = create_aiwear_agent(
        tools=tools,
        system_prompt=system_prompt,
    )
    return {"name": "visualizer", "agent": agent, "description": "图片处理助手"}


def run_visualizer(state: dict, image_urls: list = None) -> dict:
    if image_urls:
        state["image_urls"] = image_urls
    state["needs_tools"] = True
    return state
