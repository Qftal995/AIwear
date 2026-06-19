import base64
import json
import os
import time
import uuid
from io import BytesIO

from PIL import Image
import requests
from dashscope import ImageSynthesis
from dashscope.aigc import MultiModalConversation
from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_core.messages.human import HumanMessage
from langchain_core.tools import tool


def _process_image_to_uri(image_data: bytes) -> str:
    img = Image.open(BytesIO(image_data))
    image_format = img.format.lower()
    image_base64 = base64.b64encode(image_data).decode("utf-8")
    return f"data:image/{image_format};base64,{image_base64}"


def _download_image(url: str) -> bytes:
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    return resp.content


def _describe_image(data_uri: str, vl_llm: ChatTongyi) -> str:
    """用视觉模型描述图片内容，识别人物/服装特征"""
    desc_prompt = [
        {"image": data_uri},
        {"text": (
            "描述这张图片：图中有没有人？如果有，描述人物的性别、年龄感、姿势、"
            "身上穿着的服装款式和颜色、发型、背景环境。"
            "如果图中是单品服装（平铺/挂拍/模特假人），描述服装的品类、颜色、材质、款式版型。"
            "用中文简要回答，不超过120字。"
        )}
    ]
    resp = vl_llm.invoke([HumanMessage(content=desc_prompt)])
    if isinstance(resp.content, list):
        return resp.content[0].get("text", str(resp.content))
    return str(resp.content)


@tool(description="编辑单张图片，调用 wanx2.1-imageedit，返回 JSON")
def edit_image_tool(instruction: str, image_data: bytes = None, image_url: str = None) -> str:
    if image_data is None and image_url is None:
        return json.dumps({"success": False, "error": "image_data or image_url required"})
    try:
        if image_data is None:
            image_data = _download_image(image_url)
        data_uri = _process_image_to_uri(image_data)
        prompt = (
            f"编辑修改这张图片中人物的服装，改成：{instruction}。"
            f"必须保留原图中人物面部、发型、姿势、背景完全不变，只替换服装部分。"
        )
        response = ImageSynthesis.call(
            model="wanx2.1-imageedit",
            function="description_edit",
            prompt=prompt,
            base_image_url=data_uri,
            n=1,
        )
        if response.status_code != 200:
            return json.dumps({"success": False, "error": response.message}, ensure_ascii=False)
        url = response.output.results[0].url
        return json.dumps({"success": True, "url": url}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


@tool(description="合并两张图片生成试穿效果图，使用 qwen-image-edit-plus 同步生成，返回 JSON")
def merge_image_tool(instruction: str, image_data1=None, image_url1=None, image_data2=None, image_url2=None) -> str:
    if image_data1 is None and image_url1 is None:
        return json.dumps({"success": False, "error": "image_data1 or image_url1 required"})
    if image_data2 is None and image_url2 is None:
        return json.dumps({"success": False, "error": "image_data2 or image_url2 required"})

    try:
        if image_data1 is None:
            image_data1 = _download_image(image_url1)
        if image_data2 is None:
            image_data2 = _download_image(image_url2)

        data_uri1 = _process_image_to_uri(image_data1)
        data_uri2 = _process_image_to_uri(image_data2)

        vl_llm = ChatTongyi(model_name="qwen-vl-max", temperature=0.0)
        desc1 = _describe_image(data_uri1, vl_llm)
        desc2 = _describe_image(data_uri2, vl_llm)

        prompt = (
            f"图1（人物）：{desc1}\n"
            f"图2（服装）：{desc2}\n"
            f"给图1人物换上图2的服装。只迁移图2中服装的款式、颜色、版型和材质到图1人物身上。"
            f"必须保留图1人物的面部、发型、姿势、身材比例和背景完全不变。"
            f"不要复制图2中的人物、宠物、背景、表情、场景或其他物体。"
        )
        if instruction:
            prompt = f"用户需求：{instruction}\n{prompt}"

        messages = [{"role": "user", "content": [
            {"image": data_uri1},
            {"image": data_uri2},
            {"text": prompt},
        ]}]
        response = MultiModalConversation.call(model="qwen-image-edit-plus", messages=messages)
        url = response["output"]["choices"][0]["message"]["content"][0]["image"]
        return json.dumps({
            "success": True, "url": url, "model": "qwen-image-edit-plus",
            "desc1": desc1, "desc2": desc2,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


# ── 结构化执行层：接受 StructuredTask，不做智能猜测 ──────────────

def execute_virtual_tryon(person_data: bytes, garment_data: bytes,
                          garment_type: str = "unknown",
                          person_gender: str = "unknown",
                          instruction: str = "") -> dict:
    data_uri1 = _process_image_to_uri(person_data)
    data_uri2 = _process_image_to_uri(garment_data)
    prompt = (
        f"{instruction or '给图1人物换上图2的衣服'}\n"
        "只迁移图2中的服装款式、颜色、版型和材质到图1人物身上。"
        "必须保留图1人物的人脸、发型、姿势、身材比例和背景。"
        "不要复制图2中的人物、宠物、背景、姿势、表情、场景或其他物体。"
    )
    messages = [{"role": "user", "content": [
        {"image": data_uri1},
        {"image": data_uri2},
        {"text": prompt},
    ]}]
    response = MultiModalConversation.call(model="qwen-image-edit-plus", messages=messages)
    url = response["output"]["choices"][0]["message"]["content"][0]["image"]
    return {
        "success": True,
        "url": url,
        "model": "qwen-image-edit-plus",
        "task": "virtual_tryon",
        "garment_type": garment_type,
        "person_gender": person_gender,
    }
def execute_single_edit(image_data: bytes, instruction: str,
                        garment_type: str = "unknown") -> dict:
    """执行单图编辑 — wanx2.1-imageedit"""
    data_uri = _process_image_to_uri(image_data)
    prompt = (
        f"编辑修改这张图片中的服装，改成：{instruction}。"
        f"必须保留原图中人物面部、发型、姿势、背景完全不变，只替换服装部分。"
    )
    response = ImageSynthesis.call(
        model="wanx2.1-imageedit",
        function="description_edit",
        prompt=prompt,
        base_image_url=data_uri,
        n=1,
    )
    if response.status_code != 200:
        return {"success": False, "error": response.message}
    return {"success": True, "url": response.output.results[0].url, "model": "wanx2.1-imageedit"}


def execute_composite(image_data1: bytes, image_data2: bytes,
                      instruction: str, person_gender: str = "unknown") -> dict:
    """执行多图合成 — qwen-image-edit-plus"""
    data_uri1 = _process_image_to_uri(image_data1)
    data_uri2 = _process_image_to_uri(image_data2)
    messages = [{"role": "user", "content": [
        {"image": data_uri1}, {"image": data_uri2},
        {"text": f"将这两张图合成一张图。{instruction}"}
    ]}]
    response = MultiModalConversation.call(model="qwen-image-edit-plus", messages=messages)
    url = response["output"]["choices"][0]["message"]["content"][0]["image"]
    return {"success": True, "url": url, "model": "qwen-image-edit-plus"}


def execute_structured_task(task) -> dict:
    """根据结构化任务分发到对应执行器，统一记录 task_id/model/latency/status/error."""
    from tools.task_router import TaskType

    task_type_str = task.task if isinstance(task.task, str) else task.task.value
    task_id = str(uuid.uuid4())[:8]
    t0 = time.time()

    try:
        if task_type_str == "virtual_tryon":
            result = execute_virtual_tryon(
                person_data=task.person_image,
                garment_data=task.garment_image,
                garment_type=task.garment_type,
                person_gender=task.person_gender,
                instruction=task.edit_instruction or "",
            )
        elif task_type_str == "single_edit":
            result = execute_single_edit(
                image_data=task.source_image or task.person_image,
                instruction=task.edit_instruction,
                garment_type=task.garment_type,
            )
        elif task_type_str == "composite":
            result = execute_composite(
                image_data1=task.person_image,
                image_data2=task.garment_image,
                instruction=task.edit_instruction or "",
                person_gender=task.person_gender,
            )
        else:
            return {"success": False, "task_id": task_id, "task": task_type_str, "error": f"unknown task type: {task_type_str}"}

        latency_ms = int((time.time() - t0) * 1000)
        result["task_id"] = task_id
        result["task"] = result.get("task", task_type_str)
        result["latencyMs"] = latency_ms
        result["error"] = ""
        return result

    except Exception as exc:
        latency_ms = int((time.time() - t0) * 1000)
        return {
            "success": False,
            "task_id": task_id,
            "task": task_type_str,
            "model": "",
            "url": "",
            "latencyMs": latency_ms,
            "error": str(exc),
        }


# ── 原有 Agent 工具（保持向后兼容）───────────────────────────────


@tool(description="用 qwen-vl-max 描述图片，返回文本+关键词")
def image_description_tool(image_data: bytes) -> str:
    data_uri = _process_image_to_uri(image_data)
    human_content = [
        {"image": data_uri},
        {"text": "用一句话简要描述这张图片中的服装/人物，并给出3到5个关键词（颜色、品类、风格），使用逗号分隔"}
    ]
    vl_llm = ChatTongyi(model_name="qwen-vl-max", temperature=0.0)
    resp = vl_llm.invoke([HumanMessage(content=human_content)])
    return resp.content[0]["text"]
