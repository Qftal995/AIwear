class BodyShapeService:
    """Body shape analysis and dressing advice.

    Provides rule-based body shape classification and styling recommendations
    for different body types. Supports both measurement-based and image-based analysis.
    """

    SHAPE_RULES = {
        "梨形": {
            "description": "上半身纤细，臀部和大腿较丰满",
            "strategy": "平衡上下身比例，突出腰线，弱化臀腿部",
            "recommend": ["A字裙", "阔腿裤", "V领上衣", "高腰设计"],
            "avoid": ["紧身裤", "包臀裙", "夸张的臀部装饰"],
        },
        "苹果型": {
            "description": "上半身和腹部较丰满，四肢相对纤细",
            "strategy": "拉长身形，弱化腹部，突出四肢优势",
            "recommend": ["V领衬衫", "直筒连衣裙", "高腰A字裙", "七分袖"],
            "avoid": ["紧身上衣", "腰部褶皱", "宽腰带"],
        },
        "H型": {
            "description": "肩腰臀宽度相近，无明显曲线",
            "strategy": "通过廓形和层次创造曲线感",
            "recommend": ["收腰连衣裙", "衬衫+半身裙", "oversize上装+修身下装"],
            "avoid": ["直筒无腰线设计", "过于宽松的全身装"],
        },
        "倒三角": {
            "description": "肩部较宽，臀部较窄",
            "strategy": "弱化肩部，增加下半身体积感",
            "recommend": ["A字裙", "阔腿裤", "深V领口", "简洁肩部设计"],
            "avoid": ["垫肩", "泡泡袖", "横条纹上衣"],
        },
        "沙漏型": {
            "description": "肩臀比例协调，腰线明显",
            "strategy": "突出腰线优势，保持上下平衡",
            "recommend": ["收腰连衣裙", "高腰裤", "包裙", "腰带装饰"],
            "avoid": ["宽松无腰线", "过于紧身"],
        },
    }

    def analyze_from_image(self, image_url: str) -> dict:
        """Analyze body shape from a photo using qwen-vl-max vision model."""
        import requests
        from langchain_community.chat_models.tongyi import ChatTongyi
        from langchain_core.messages.human import HumanMessage
        import base64
        from io import BytesIO

        try:
            resp = requests.get(image_url, timeout=20)
            resp.raise_for_status()
            image_data = resp.content
        except Exception as e:
            return {"shape": "unknown", "note": f"图片下载失败: {e}"}

        try:
            from PIL import Image
            img = Image.open(BytesIO(image_data))
            fmt = img.format.lower()
            img_b64 = base64.b64encode(image_data).decode("utf-8")
            data_uri = f"data:image/{fmt};base64,{img_b64}"
        except Exception:
            data_uri = f"data:image/jpeg;base64,{base64.b64encode(image_data).decode('utf-8')}"

        prompt = [
            {"image": data_uri},
            {"text": (
                "请仔细分析照片中人物的身材特征，判断属于哪种身材类型（梨形/苹果型/H型/倒三角/沙漏型）。"
                "分析依据：肩宽、腰线、臀胯比例、整体轮廓。"
                "返回JSON格式，只返回JSON不要其他内容："
                '{"shape": "身材类型", "confidence": "high/medium/low", "reason": "简要判断依据"}'
            )}
        ]
        try:
            vl_llm = ChatTongyi(model_name="qwen-vl-max", temperature=0.0)
            resp = vl_llm.invoke([HumanMessage(content=prompt)])
            content = resp.content if isinstance(resp.content, str) else resp.content[0].get("text", str(resp.content))

            # Parse JSON from response
            content = content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            import json
            parsed = json.loads(content)
            shape = parsed.get("shape", "unknown")
            if shape not in self.SHAPE_RULES:
                # Try keyword matching as fallback
                return self._from_description(parsed.get("reason", ""))
            return {
                "shape": shape,
                "confidence": parsed.get("confidence", "medium"),
                "reason": parsed.get("reason", ""),
                **self.SHAPE_RULES.get(shape, {}),
                "analysis_method": "image_vision",
            }
        except Exception as e:
            return {"shape": "unknown", "note": f"视觉分析失败: {e}", "analysis_method": "image_vision"}

    def analyze(self, measurements: dict = None, description: str = "") -> dict:
        """Analyze body shape from measurements or text description."""
        if measurements:
            return self._from_measurements(measurements)
        if description:
            return self._from_description(description)
        return {"shape": "unknown", "note": "需要提供身材数据或描述"}

    def _from_measurements(self, m: dict) -> dict:
        bust = float(m.get("bust", 0))
        waist = float(m.get("waist", 0))
        hip = float(m.get("hip", 0))
        if not all([bust, waist, hip]):
            return {"shape": "unknown", "note": "需要胸围、腰围、臀围数据"}

        bwr = bust / waist if waist > 0 else 0
        whr = waist / hip if hip > 0 else 0

        if bwr > 1.3 and whr < 0.85:
            shape = "倒三角"
        elif bwr < 1.2 and whr > 0.85:
            shape = "梨形"
        elif bwr > 1.2 and whr > 0.85:
            shape = "苹果型"
        elif 1.15 <= bwr <= 1.35 and 0.7 <= whr <= 0.8:
            shape = "沙漏型"
        else:
            shape = "H型"

        return self._result(shape)

    def _from_description(self, desc: str) -> dict:
        keywords = {
            "梨形": ["下半身", "臀部", "大腿", "胯宽", "梨形"],
            "苹果型": ["腹部", "肚子", "上半身胖", "苹果型", "圆身"],
            "H型": ["没有腰", "直筒", "H型", "直上直下"],
            "倒三角": ["肩宽", "倒三角", "肩部宽"],
            "沙漏型": ["沙漏", "有腰", "曲线", "S型"],
        }
        for shape, kws in keywords.items():
            if any(kw in desc for kw in kws):
                return self._result(shape)
        return {"shape": "unknown", "note": "无法从描述中识别身材类型，建议提供更详细信息"}

    def _result(self, shape: str) -> dict:
        rule = self.SHAPE_RULES.get(shape, {})
        return {"shape": shape, **rule}

    def list_shapes(self) -> list[dict]:
        return [
            {"shape": k, "description": v["description"]}
            for k, v in self.SHAPE_RULES.items()
        ]
