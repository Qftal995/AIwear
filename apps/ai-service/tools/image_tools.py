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


DASHSCOPE_FILES_URL = "https://dashscope.aliyuncs.com/api/v1/files"


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


def _upload_via_dashscope(image_data: bytes) -> tuple:
    """通过 DashScope Files API 上传图片，返回 (url, file_id)"""
    api_key = os.getenv("DASHSCOPE_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}"}

    ext = "png"
    try:
        img = Image.open(BytesIO(image_data))
        ext = img.format.lower()
    except Exception:
        pass

    filename = f"{uuid.uuid4().hex}.{ext}"

    upload_resp = requests.post(
        DASHSCOPE_FILES_URL,
        headers=headers,
        files={"files": (filename, image_data, f"image/{ext}")},
        data={"purpose": "file-extract"},
        timeout=30,
    )
    upload_resp.raise_for_status()
    file_id = upload_resp.json()["data"]["uploaded_files"][0]["file_id"]

    detail_resp = requests.get(
        f"{DASHSCOPE_FILES_URL}/{file_id}",
        headers=headers,
        timeout=30,
    )
    detail_resp.raise_for_status()
    url = detail_resp.json()["data"]["url"]
    return url, file_id


def _delete_dashscope_file(file_id: str):
    """删除 DashScope 临时文件"""
    try:
        api_key = os.getenv("DASHSCOPE_API_KEY")
        requests.delete(
            f"{DASHSCOPE_FILES_URL}/{file_id}",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
    except Exception:
        pass


def _outfitanyone_tryon(person_url: str, top_url: str, bottom_url: str = None) -> dict:
    """调用 OutfitAnyone aitryon-plus 虚拟试衣 API（异步提交+轮询）"""
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        return {"success": False, "error": "DASHSCOPE_API_KEY not set"}

    body = {
        "model": "aitryon-plus",
        "input": {
            "person_image_url": person_url,
            "top_garment_url": top_url,
        },
        "parameters": {
            "resolution": -1,
            "restore_face": True,
        },
    }
    if bottom_url:
        body["input"]["bottom_garment_url"] = bottom_url

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "X-DashScope-Async": "enable",
    }

    submit_resp = requests.post(
        "https://dashscope.aliyuncs.com/api/v1/services/aigc/image2image/image-synthesis",
        json=body,
        headers=headers,
        timeout=30,
    )
    submit_resp.raise_for_status()
    submit_result = submit_resp.json()
    task_id = submit_result.get("output", {}).get("task_id")
    if not task_id:
        return {"success": False, "error": f"submit failed: {submit_result.get('message', 'no task_id')}"}

    query_url = f"https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
    for _ in range(60):
        time.sleep(5)
        q_resp = requests.get(query_url, headers={"Authorization": f"Bearer {api_key}"}, timeout=10)
        q_resp.raise_for_status()
        q_result = q_resp.json()
        status = q_result["output"]["task_status"]
        if status == "SUCCEEDED":
            url = q_result["output"]["results"][0]["url"]
            return {"success": True, "url": url, "model": "aitryon-plus"}
        elif status == "FAILED":
            return {"success": False, "error": q_result["output"].get("message", "task failed")}

    return {"success": False, "error": "timeout after 5min"}


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


@tool(description="合并两张图片，通过 DashScope Files 获取公网 URL 后调用 OutfitAnyone 试衣，返回 JSON")
def merge_image_tool(instruction: str, image_data1=None, image_url1=None, image_data2=None, image_url2=None) -> str:
    if image_data1 is None and image_url1 is None:
        return json.dumps({"success": False, "error": "image_data1 or image_url1 required"})
    if image_data2 is None and image_url2 is None:
        return json.dumps({"success": False, "error": "image_data2 or image_url2 required"})

    file_ids_to_clean = []
    try:
        if image_data1 is None:
            image_data1 = _download_image(image_url1)
        if image_data2 is None:
            image_data2 = _download_image(image_url2)

        # 通过 DashScope Files API 上传，获取云内可访问的 URL
        url1, fid1 = _upload_via_dashscope(image_data1)
        file_ids_to_clean.append(fid1)
        url2, fid2 = _upload_via_dashscope(image_data2)
        file_ids_to_clean.append(fid2)

        # 调用 OutfitAnyone 专业试衣模型
        result = _outfitanyone_tryon(url1, url2)
        if result["success"]:
            return json.dumps(result, ensure_ascii=False)

        # OutfitAnyone 失败，回退 qwen-image-edit-plus
        data_uri1 = _process_image_to_uri(image_data1)
        data_uri2 = _process_image_to_uri(image_data2)

        vl_llm = ChatTongyi(model_name="qwen-vl-max", temperature=0.0)
        desc1 = _describe_image(data_uri1, vl_llm)
        desc2 = _describe_image(data_uri2, vl_llm)

        prompt = (
            f"图1内容：{desc1}\n"
            f"图2内容：{desc2}\n"
            f"用户需求：{instruction}\n"
            f"请根据图1和图2的实际内容，智能判断需要做什么（换装/合影/组合搭配等），然后完成合成。"
            f"若涉及人物换装，必须保留人物的面部、发型、姿势、背景完全不变。"
            f"若图1和图2都是人物，则让他们合影或互动。"
        )
        messages = [{"role": "user", "content": [{"image": data_uri1}, {"image": data_uri2}, {"text": prompt}]}]
        response = MultiModalConversation.call(model="qwen-image-edit-plus", messages=messages)
        url = response["output"]["choices"][0]["message"]["content"][0]["image"]
        return json.dumps({
            "success": True, "url": url, "model": "qwen-image-edit-plus",
            "desc1": desc1, "desc2": desc2,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
    finally:
        for fid in file_ids_to_clean:
            _delete_dashscope_file(fid)


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
