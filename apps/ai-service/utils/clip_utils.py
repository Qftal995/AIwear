import os
import threading
from io import BytesIO

from PIL import Image

CLIP_MODEL_DIR = os.getenv(
    "CLIP_MODEL_DIR",
    r"D:\Java仓\code\AIWear-master\代码\AIWearPython\openai-mirror\clip-vit-base-patch16",
)
_clip_model = None
_clip_processor = None
_clip_lock = threading.Lock()
_clip_available = None


def _ensure_clip():
    """Lazy-import torch and transformers. Returns True if CLIP is available."""
    global _clip_available
    if _clip_available is not None:
        return _clip_available
    try:
        global torch, CLIPModel, CLIPProcessor
        import torch
        from transformers import CLIPModel, CLIPProcessor
        _clip_available = True
    except ImportError:
        _clip_available = False
    return _clip_available


def get_clip_model_and_processor():
    if not _ensure_clip():
        raise RuntimeError("CLIP not available: torch/transformers not installed")
    global _clip_model, _clip_processor
    if _clip_model is not None and _clip_processor is not None:
        return _clip_model, _clip_processor
    with _clip_lock:
        if _clip_model is None or _clip_processor is None:
            _clip_processor = CLIPProcessor.from_pretrained(CLIP_MODEL_DIR)
            _clip_model = CLIPModel.from_pretrained(CLIP_MODEL_DIR)
            _clip_model.eval()
    return _clip_model, _clip_processor


def clip_image_to_512d(image_data: bytes) -> list[float]:
    if not _ensure_clip():
        raise RuntimeError("CLIP not available: torch/transformers not installed")
    model, processor = get_clip_model_and_processor()
    img = Image.open(BytesIO(image_data)).convert("RGB")
    inputs = processor(images=img, return_tensors="pt")
    with torch.no_grad():
        out = model.get_image_features(**inputs)
        if hasattr(out, "pooler_output") and out.pooler_output is not None:
            image_features = out.pooler_output
        elif hasattr(out, "image_embeds") and out.image_embeds is not None:
            image_features = out.image_embeds
        else:
            image_features = out
        image_features = image_features / image_features.norm(dim=-1, keepdim=True)
    vec = image_features[0].detach().cpu().tolist()
    if len(vec) != 512:
        raise ValueError(f"CLIP embedding dimension expected 512, got {len(vec)}")
    return [round(float(x), 6) for x in vec]


def cosine_similarity_512(a: list, b: list) -> float:
    if a is None or b is None:
        return 0.0
    if len(a) != 512 or len(b) != 512:
        return 0.0
    try:
        s = sum(float(a[i]) * float(b[i]) for i in range(512))
        return float(s)
    except Exception:
        return 0.0
