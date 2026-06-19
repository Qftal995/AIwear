"""图片分析器 — 用视觉模型分析图片内容，输出结构化 JSON"""
import json
import re
from io import BytesIO

from PIL import Image
from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_core.messages.human import HumanMessage


def _to_data_uri(image_data: bytes) -> str:
    img = Image.open(BytesIO(image_data))
    fmt = img.format.lower()
    b64 = __import__("base64").b64encode(image_data).decode("utf-8")
    return f"data:image/{fmt};base64,{b64}"


ANALYSIS_PROMPT = """分析这张图片，严格按以下 JSON 格式返回，不要输出任何其他内容：

{
  "has_person": true/false,
  "is_garment_item": true/false,
  "is_model_wearing": true/false,
  "subject_gender": "male"/"female"/"unknown",
  "garment_category": "top"/"bottom"/"dress"/"coat"/"full_suit"/"unknown",
  "description": "简短中文描述，不超过30字"
}

判断规则：
- has_person: 图中是否有真人（模特/自拍/街拍），假人模特不算
- is_garment_item: 是否是服装单品（平铺/挂拍/白底商品图/假人模特展示）
- is_model_wearing: 是否是真人模特穿搭图（真人穿着服装展示）
- subject_gender: 如果有真人，判断性别；否则 unknown
- garment_category:
    "top"=上衣/T恤/衬衫/毛衣/卫衣,
    "bottom"=裤子/裙子/半身裙,
    "dress"=连衣裙/连体裤,
    "coat"=外套/夹克/大衣/羽绒服,
    "full_suit"=全身套装/西装套装/运动套装,
    "unknown"=无法判断
- description: 图中内容简述"""


def analyze_image(image_data: bytes, vl_llm=None) -> dict:
    """分析单张图片，返回结构化 dict"""
    if vl_llm is None:
        vl_llm = ChatTongyi(model_name="qwen-vl-max", temperature=0.0)

    data_uri = _to_data_uri(image_data)
    resp = vl_llm.invoke([HumanMessage(content=[
        {"image": data_uri},
        {"text": ANALYSIS_PROMPT},
    ])])

    raw = resp.content
    if isinstance(raw, list):
        raw = raw[0].get("text", str(raw))

    result = _parse_analysis(raw)
    result["_image_data"] = image_data
    result["_orig_image_data"] = image_data
    return result


def _parse_analysis(raw: str) -> dict:
    """从 VL 模型返回中提取 JSON"""
    # 尝试匹配 ```json ... ``` 或裸 JSON
    json_str = raw
    m = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', raw)
    if m:
        json_str = m.group(1)
    else:
        # 尝试匹配裸 JSON 对象
        m = re.search(r'\{[\s\S]*\}', raw)
        if m:
            json_str = m.group(0)

    try:
        result = json.loads(json_str)
    except json.JSONDecodeError:
        return {
            "has_person": False,
            "is_garment_item": False,
            "is_model_wearing": False,
            "subject_gender": "unknown",
            "garment_category": "unknown",
            "description": raw[:100],
            "_parse_error": True,
        }

    # 类型规范化
    for key in ["has_person", "is_garment_item", "is_model_wearing"]:
        if key in result:
            result[key] = bool(result[key])
    valid_genders = {"male", "female", "unknown"}
    if result.get("subject_gender") not in valid_genders:
        result["subject_gender"] = "unknown"
    valid_cats = {"top", "bottom", "dress", "coat", "full_suit", "unknown"}
    if result.get("garment_category") not in valid_cats:
        result["garment_category"] = "unknown"

    return result


def analyze_pair(image_data1: bytes, image_data2: bytes, vl_llm=None) -> dict:
    """同时分析两张图片，返回分别的分析结果"""
    if vl_llm is None:
        vl_llm = ChatTongyi(model_name="qwen-vl-max", temperature=0.0)

    return {
        "image1": analyze_image(image_data1, vl_llm),
        "image2": analyze_image(image_data2, vl_llm),
    }
