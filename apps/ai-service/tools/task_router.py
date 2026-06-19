"""Image task router.

Turns image analysis + user instruction into a deterministic structured task.
The router is intentionally conservative: user intent wins, then image content.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TaskType(str, Enum):
    VIRTUAL_TRYON = "virtual_tryon"
    SINGLE_EDIT = "single_edit"
    COMPOSITE = "composite"


@dataclass
class StructuredTask:
    task: TaskType
    person_image: Optional[bytes] = None
    garment_image: Optional[bytes] = None
    garment_type: Optional[str] = None
    person_gender: Optional[str] = None
    source_image: Optional[bytes] = None
    edit_instruction: Optional[str] = None
    preserve: list = field(default_factory=lambda: ["face", "hair", "pose", "background"])
    reasoning: str = ""


SWAP_KEYWORDS = ("换上", "换装", "试穿", "穿上", "换成", "衣服", "试衣")
MERGE_KEYWORDS = ("合影", "合照", "拼接", "组合", "放到一起", "同框")
EDIT_KEYWORDS = ("改成", "改为", "变色", "换色", "修改", "调整", "去掉", "增加")


def _img(analysis: dict) -> Optional[bytes]:
    return analysis.get("_image_data") or analysis.get("_orig_image_data")


def _looks_like_garment_source(analysis: dict) -> bool:
    return bool(
        analysis.get("is_garment_item")
        or analysis.get("is_model_wearing")
        or analysis.get("garment_category") not in (None, "", "unknown")
    )


def _is_swap_instruction(instruction: str) -> bool:
    return any(keyword in instruction for keyword in SWAP_KEYWORDS)


def route(analysis_pair: dict, instruction: str, vl_llm=None) -> StructuredTask:
    """Route two-image tasks.

    For virtual try-on, a model-wearing reference image can still be a garment
    source. We avoid defaulting two-person inputs to "composite" when the user
    explicitly asks for changing clothes.
    """
    a1 = analysis_pair.get("image1", {})
    a2 = analysis_pair.get("image2", {})
    img1 = _img(a1)
    img2 = _img(a2)

    has_person_1 = bool(a1.get("has_person"))
    has_person_2 = bool(a2.get("has_person"))
    garment_1 = _looks_like_garment_source(a1)
    garment_2 = _looks_like_garment_source(a2)

    is_swap = _is_swap_instruction(instruction)
    is_merge = any(keyword in instruction for keyword in MERGE_KEYWORDS)
    is_edit = any(keyword in instruction for keyword in EDIT_KEYWORDS)

    if is_swap:
        if has_person_1 and garment_2:
            return StructuredTask(
                task=TaskType.VIRTUAL_TRYON,
                person_image=img1,
                garment_image=img2,
                garment_type=a2.get("garment_category", "unknown"),
                person_gender=a1.get("subject_gender", "unknown"),
                edit_instruction=instruction,
                reasoning="swap intent: image1 person, image2 garment source",
            )
        if has_person_2 and garment_1:
            return StructuredTask(
                task=TaskType.VIRTUAL_TRYON,
                person_image=img2,
                garment_image=img1,
                garment_type=a1.get("garment_category", "unknown"),
                person_gender=a2.get("subject_gender", "unknown"),
                edit_instruction=instruction,
                reasoning="swap intent: image2 person, image1 garment source",
            )
        return StructuredTask(
            task=TaskType.COMPOSITE,
            person_image=img1,
            garment_image=img2,
            edit_instruction=_tryon_prompt(instruction),
            reasoning="swap intent but ambiguous image roles; use constrained image edit",
        )

    if is_merge or (has_person_1 and has_person_2):
        return StructuredTask(
            task=TaskType.COMPOSITE,
            person_image=img1,
            garment_image=img2,
            edit_instruction=instruction,
            reasoning="composite intent or two-person composition",
        )

    if is_edit:
        source = img1 if has_person_1 or garment_1 else img2
        return StructuredTask(
            task=TaskType.SINGLE_EDIT,
            source_image=source,
            edit_instruction=instruction,
            garment_type=(a1 if source is img1 else a2).get("garment_category", "unknown"),
            reasoning="edit intent",
        )

    return StructuredTask(
        task=TaskType.COMPOSITE,
        person_image=img1,
        garment_image=img2,
        edit_instruction=instruction,
        reasoning="default two-image edit",
    )


def route_single(image_analysis: dict, instruction: str) -> StructuredTask:
    return StructuredTask(
        task=TaskType.SINGLE_EDIT,
        source_image=_img(image_analysis),
        edit_instruction=instruction,
        garment_type=image_analysis.get("garment_category", "unknown"),
        person_gender=image_analysis.get("subject_gender", "unknown"),
        reasoning="single image edit",
    )


def _tryon_prompt(instruction: str) -> str:
    return (
        f"{instruction}\n"
        "If this is virtual try-on, use the first suitable image as the target person "
        "and the other image only as a garment/style reference. Preserve the target "
        "person's face, hair, pose, body proportion, and background. Do not copy any "
        "extra person, animal, object, background, pose, or scene from the reference image."
    )
