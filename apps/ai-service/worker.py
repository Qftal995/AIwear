"""AIWear 图片任务 Worker — 从 RabbitMQ 消费异步图片处理任务"""
import os
import sys
import base64

import requests
from dotenv import load_dotenv

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(dotenv_path=os.path.join(_project_root, ".env"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _download_image(url: str) -> bytes:
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    return resp.content


# ---- Task Handlers —— 识别 → 路由 → 生成 三段式 ─-------------------


def _load_images(payload: dict) -> tuple:
    """从 payload 中解析图片数据，返回 (image_data, image_url) 或 (image_data1, image_data2, ...)"""
    instruction = payload.get("instruction", "")

    # 双图模式 (merge)
    if "image_data1_b64" in payload or "image_url1" in payload:
        d1, d2 = None, None
        if payload.get("image_data1_b64"):
            d1 = base64.b64decode(payload["image_data1_b64"])
        elif payload.get("image_url1"):
            d1 = _download_image(payload["image_url1"])
        if payload.get("image_data2_b64"):
            d2 = base64.b64decode(payload["image_data2_b64"])
        elif payload.get("image_url2"):
            d2 = _download_image(payload["image_url2"])
        if not d1 or not d2:
            raise ValueError("image1 and image2 required")
        return ("pair", d1, d2, instruction)

    # 单图模式 (edit)
    if payload.get("image_data_b64"):
        d = base64.b64decode(payload["image_data_b64"])
    elif payload.get("image_url"):
        d = _download_image(payload["image_url"])
    else:
        raise ValueError("image_url or image_data_b64 required")
    return ("single", d, instruction)


def handle_edit(payload: dict) -> dict:
    try:
        mode, image_data, instruction = _load_images(payload)

        # ① 识别: 分析单张图片
        from tools.image_analyzer import analyze_image
        analysis = analyze_image(image_data)
        analysis["_orig_image_data"] = image_data

        # ② 路由: 判断任务类型
        from tools.task_router import route_single
        task = route_single(analysis, instruction)

        # ③ 生成: 执行结构化任务
        from tools.image_tools import execute_structured_task
        return execute_structured_task(task)

    except Exception as e:
        return {"success": False, "error": str(e)}


def handle_merge(payload: dict) -> dict:
    try:
        mode, image_data1, image_data2, instruction = _load_images(payload)

        # ① 识别: 分析两张图片
        from tools.image_analyzer import analyze_pair
        analysis = analyze_pair(image_data1, image_data2)
        analysis["image1"]["_orig_image_data"] = image_data1
        analysis["image2"]["_orig_image_data"] = image_data2

        # ② 路由: 据分析结果 + 用户指令 → 结构化任务
        from tools.task_router import route
        task = route(analysis, instruction)

        # ③ 生成: 执行结构化任务
        from tools.image_tools import execute_structured_task
        return execute_structured_task(task)

    except Exception as e:
        return {"success": False, "error": str(e)}


HANDLERS = {
    "edit": handle_edit,
    "merge": handle_merge,
}


def main():
    from utils.mq import TaskConsumer
    consumer = TaskConsumer(handlers=HANDLERS)
    try:
        consumer.start()
    except KeyboardInterrupt:
        consumer.stop()
        print("[MQ] Worker stopped")


if __name__ == "__main__":
    main()
