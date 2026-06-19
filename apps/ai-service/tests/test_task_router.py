"""Task router unit tests — verify routing logic for all task types."""

import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.task_router import route, route_single, TaskType, StructuredTask

# ── Fixtures ────────────────────────────────────────────────────────

def _analysis(has_person=True, garment_category="", is_garment_item=False, is_model_wearing=False, subject_gender="unknown"):
    return {
        "has_person": has_person,
        "garment_category": garment_category,
        "is_garment_item": is_garment_item,
        "is_model_wearing": is_model_wearing,
        "subject_gender": subject_gender,
    }


PERSON_IMG = _analysis(has_person=True, subject_gender="male")
GARMENT_IMG = _analysis(has_person=False, garment_category="top", is_garment_item=True)
MODEL_IMG = _analysis(has_person=True, garment_category="dress", is_model_wearing=True, subject_gender="female")
PERSON2_IMG = _analysis(has_person=True, subject_gender="female")

# ── route (two-image) tests ─────────────────────────────────────────


class TestRouteVirtualTryon:
    def test_person_plus_garment_swap_intent(self):
        pair = {"image1": PERSON_IMG, "image2": GARMENT_IMG}
        task = route(pair, "帮我把衣服换上")
        assert task.task == TaskType.VIRTUAL_TRYON

    def test_person_plus_model_swap_intent(self):
        pair = {"image1": PERSON_IMG, "image2": MODEL_IMG}
        task = route(pair, "换上这件裙子")
        assert task.task == TaskType.VIRTUAL_TRYON

    def test_swap_intent_person_in_image2(self):
        pair = {"image1": GARMENT_IMG, "image2": PERSON_IMG}
        task = route(pair, "给他穿上这件")
        assert task.task == TaskType.VIRTUAL_TRYON
        assert task.person_gender == "male"

    def test_swap_intent_ambiguous_roles_falls_back_to_composite(self):
        pair = {"image1": PERSON_IMG, "image2": PERSON2_IMG}
        task = route(pair, "换上这件衣服")
        assert task.task == TaskType.COMPOSITE


class TestRouteComposite:
    def test_two_people_merge(self):
        pair = {"image1": PERSON_IMG, "image2": PERSON2_IMG}
        task = route(pair, "来张合影")
        assert task.task == TaskType.COMPOSITE

    def test_two_people_no_instruction(self):
        pair = {"image1": PERSON_IMG, "image2": PERSON2_IMG}
        task = route(pair, "随便处理一下")
        assert task.task == TaskType.COMPOSITE


class TestRouteSingleEdit:
    def test_edit_instruction(self):
        pair = {"image1": PERSON_IMG, "image2": GARMENT_IMG}
        task = route(pair, "把衬衫改成红色")
        assert task.task == TaskType.SINGLE_EDIT


# ── route_single (single-image) tests ────────────────────────────────


class TestRouteSingle:
    def test_always_single_edit(self):
        task = route_single(PERSON_IMG, "改成黑色")
        assert task.task == TaskType.SINGLE_EDIT
        assert task.edit_instruction == "改成黑色"

    def test_preserves_gender(self):
        task = route_single(PERSON_IMG, "修改")
        assert task.person_gender == "male"


# ── Edge cases ──────────────────────────────────────────────────────


class TestEdgeCases:
    def test_garment_only_images(self):
        pair = {"image1": GARMENT_IMG, "image2": GARMENT_IMG}
        task = route(pair, "帮我搭配一下")
        assert task.task == TaskType.COMPOSITE

    def test_empty_instruction(self):
        pair = {"image1": PERSON_IMG, "image2": GARMENT_IMG}
        task = route(pair, "")
        assert task.task == TaskType.COMPOSITE

    def test_swap_keyword_in_complex_sentence(self):
        pair = {"image1": PERSON_IMG, "image2": GARMENT_IMG}
        task = route(pair, "我想把这件衣服换上看看效果怎么样")
        assert task.task == TaskType.VIRTUAL_TRYON

    def test_virtual_tryon_preserve_instruction(self):
        pair = {"image1": PERSON_IMG, "image2": GARMENT_IMG}
        task = route(pair, "把衣服换上红色的")
        assert task.task == TaskType.VIRTUAL_TRYON
        assert task.edit_instruction is not None
